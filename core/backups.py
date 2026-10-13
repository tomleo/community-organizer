"""Off-site backups with restic: a database dump plus the media folder, verified weekly."""

import json
import logging
import os
import shutil
import subprocess
import time as time_module
import urllib.error
import urllib.request
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import mail_admins
from django.db import close_old_connections
from django.utils import timezone

from organization.models import BackupRun, SiteSettings

logger = logging.getLogger(__name__)

DUMP_NAME = "database.dump"
KEEP = ["--keep-daily", "7", "--keep-weekly", "4", "--keep-monthly", "12"]
REPOSITORY_MISSING = 10  # restic's exit code when the repository doesn't exist yet
# Containers get random host names and restic applies retention per host, so use one name.
RESTIC_HOST = "community-organizer"
MESSAGE_LIMIT = 2000
RETENTION = timedelta(days=90)
STALE_AFTER = timedelta(days=2)
SUNDAY = 6
RESET_SCHEMA_SQL = "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
# Fails the restore test unless the main tables exist; the first number is the user count.
RESTORE_CHECK_SQL = (
    "SELECT count(*) FROM auth_user; "
    "SELECT count(*) FROM events_event; "
    "SELECT count(*) FROM registrations_registration;"
)


class BackupError(Exception):
    def __init__(self, step: str, output: str):
        super().__init__(output)
        self.step = step


def configured() -> bool:
    return bool(os.environ.get("RESTIC_REPOSITORY"))


def postgres_env() -> dict:
    """Environment for restic and the PostgreSQL client tools (libpq reads PG* variables)."""
    database = settings.DATABASES["default"]
    return {
        **os.environ,
        "PGHOST": database["HOST"],
        "PGPORT": str(database["PORT"] or 5432),
        "PGUSER": database["USER"],
        "PGPASSWORD": database["PASSWORD"],
        "PGDATABASE": database["NAME"],
    }


def run(step: str, args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, env=postgres_env())
    if result.returncode != 0:
        raise BackupError(step, (result.stderr or result.stdout).strip() or f"{args[0]} failed")
    return result.stdout


def backup_once(kind: str, *, now=None, echo=None) -> BackupRun | None:
    """Run one backup and record it. Returns None if "not configured" was already recorded today."""
    now = now or timezone.now()
    echo = echo or (lambda message: None)
    if not configured():
        return _record_not_configured(now)
    record = BackupRun.objects.create(kind=kind, started_at=now)
    work = Path(settings.BACKUP_WORK_DIR)
    step = "upload"
    try:
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        _ensure_repository()
        step = "dump"
        echo("Dumping the database…")
        dump = work / DUMP_NAME
        run(step, ["pg_dump", "--format=custom", "--file", str(dump)])
        step = "upload"
        echo("Uploading to the backup repository…")
        record.snapshot_id = _upload(dump, kind)
        step = "prune"
        echo("Removing old snapshots…")
        run(step, ["restic", "forget", "--prune", *KEEP])
        if kind == BackupRun.Kind.NIGHTLY and _site_time(now).weekday() == SUNDAY:
            step = "check"
            echo("Checking the repository…")
            run(step, ["restic", "check", "--read-data-subset=5%"])
            step = "restore_test"
            echo("Test-restoring the database…")
            _restore_test(work, now)
    except BackupError as exc:
        _fail(record, exc.step, str(exc))
    except Exception as exc:
        logger.exception("Backup crashed at %s", step)
        _fail(record, step, f"{type(exc).__name__}: {exc}")
    else:
        _finish(record, ok=True, step=step)
        echo(f"Backup finished: snapshot {record.snapshot_id}.")
    finally:
        shutil.rmtree(work, ignore_errors=True)
        BackupRun.objects.filter(started_at__lt=now - RETENTION).delete()
    return record


WAKE_INTERVAL = 600  # seconds; re-read the time zone and BACKUP_TIME at least this often


def parse_backup_time(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise ImproperlyConfigured(f"BACKUP_TIME must look like 03:00, got {value!r}.") from exc


def next_run(now: datetime, backup_time: time, tz) -> datetime:
    """The next BACKUP_TIME (wall-clock time in `tz`) after `now`, in UTC."""
    local = now.astimezone(tz)
    candidate = datetime.combine(local.date(), backup_time, tzinfo=tz)
    if candidate <= local:
        candidate = datetime.combine(local.date() + timedelta(days=1), backup_time, tzinfo=tz)
    return candidate.astimezone(UTC)


def run_forever(*, sleep=time_module.sleep, clock=timezone.now, max_runs=None) -> None:
    """The backup service's loop: one nightly backup at BACKUP_TIME, site time."""
    runs = 0
    while max_runs is None or runs < max_runs:
        close_old_connections()
        tz = ZoneInfo(SiteSettings.load().time_zone)
        due = next_run(clock(), parse_backup_time(settings.BACKUP_TIME), tz)
        wait = (due - clock()).total_seconds()
        if wait > WAKE_INTERVAL:
            sleep(WAKE_INTERVAL)
            continue
        sleep(max(wait, 0))
        try:
            backup_once(BackupRun.Kind.NIGHTLY, now=clock())
        except Exception:
            logger.exception("The backup run crashed; trying again tomorrow.")
        runs += 1


def site_is_up(url=None) -> bool:
    """True if the web service answers at all — even a 503 means it's still running."""
    try:
        with urllib.request.urlopen(url or settings.BACKUP_HEALTH_URL, timeout=3):
            return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def describe_snapshot(snapshot: str) -> dict:
    output = run("restore", ["restic", "snapshots", "--json", snapshot])
    found = json.loads(output or "[]")
    if not found:
        raise BackupError("restore", f"No snapshot {snapshot!r} in the repository.")
    return {"id": found[-1]["short_id"], "time": found[-1]["time"]}


def restore(snapshot: str, *, echo) -> None:
    """Replace the database and media files with a snapshot's. The site must be stopped."""
    work = Path(settings.BACKUP_WORK_DIR)
    target = work / "restore"
    media = Path(settings.MEDIA_ROOT)
    shutil.rmtree(work, ignore_errors=True)
    try:
        echo("Downloading the snapshot…")
        run("restore", ["restic", "restore", snapshot, "--target", str(target)])
        echo("Restoring the database…")
        dump = target / str(work / DUMP_NAME).lstrip("/")
        database = settings.DATABASES["default"]["NAME"]
        # Start from an empty schema: a backup made before newer migrations must not mix with them.
        run(
            "restore",
            ["psql", "--dbname", database, "-v", "ON_ERROR_STOP=1", "--command", RESET_SCHEMA_SQL],
        )
        run(
            "restore",
            [
                "pg_restore",
                "--no-owner",
                "--single-transaction",
                "--exit-on-error",
                "--dbname",
                database,
                str(dump),
            ],
        )
        echo("Restoring media files…")
        _replace_contents(media, target / str(media).lstrip("/"))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _replace_contents(folder: Path, source: Path) -> None:
    """Empty `folder` but keep it (it may be a volume's mount point), then move `source` in."""
    folder.mkdir(parents=True, exist_ok=True)
    for child in folder.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    if source.is_dir():
        for child in source.iterdir():
            shutil.move(str(child), folder / child.name)


def backup_status(now=None) -> dict:
    """What the Site settings page says about backups, from the runs the backup service recorded."""
    now = now or timezone.now()
    last_ok = BackupRun.objects.filter(ok=True).first()
    latest = BackupRun.objects.filter(finished_at__isnull=False).first()
    last_ok_at = last_ok.started_at if last_ok else None
    if latest is None:
        return {"warning": True, "text": "No backup has run yet.", "last_ok": None}
    if latest.step == "not_configured":
        text = (
            "Backups are not configured. "
            "Set RESTIC_REPOSITORY and RESTIC_PASSWORD (see docs/deployment.md)."
        )
        return {"warning": True, "text": text, "last_ok": last_ok_at}
    if not latest.ok:
        first_line = latest.message.splitlines()[0] if latest.message else ""
        text = f"The latest backup failed ({latest.step}): {first_line}"
        return {"warning": True, "text": text, "last_ok": last_ok_at}
    if last_ok_at is None or now - last_ok_at > STALE_AFTER:
        text = "No successful backup in the last 2 days."
        return {"warning": True, "text": text, "last_ok": last_ok_at}
    return {"warning": False, "text": "", "last_ok": last_ok_at}


def _site_time(now):
    return now.astimezone(ZoneInfo(SiteSettings.load().time_zone))


def _record_not_configured(now) -> BackupRun | None:
    if BackupRun.objects.filter(
        step="not_configured", started_at__gt=now - timedelta(days=1)
    ).exists():
        return None
    logger.warning("Backups are not configured: set RESTIC_REPOSITORY and RESTIC_PASSWORD.")
    return BackupRun.objects.create(
        kind=BackupRun.Kind.NIGHTLY,
        started_at=now,
        finished_at=now,
        ok=False,
        step="not_configured",
        message="RESTIC_REPOSITORY is not set.",
    )


def _ensure_repository() -> None:
    result = subprocess.run(
        ["restic", "cat", "config"], capture_output=True, text=True, env=postgres_env()
    )
    if result.returncode == REPOSITORY_MISSING:
        run("upload", ["restic", "init"])
    elif result.returncode != 0:
        raise BackupError("upload", result.stderr.strip() or "Can't open the backup repository.")


def _upload(dump: Path, kind: str) -> str:
    media = Path(settings.MEDIA_ROOT)
    media.mkdir(parents=True, exist_ok=True)
    output = run(
        "upload",
        ["restic", "backup", "--json", "--host", RESTIC_HOST, "--tag", kind, str(dump), str(media)],
    )
    for line in reversed(output.splitlines()):
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("message_type") == "summary":
            return message["snapshot_id"]
    raise BackupError("upload", "restic didn't report a snapshot id.")


def _restore_test(work: Path, now) -> None:
    target = work / "restore-test"
    dump = work / DUMP_NAME
    run(
        "restore_test",
        ["restic", "restore", "latest", "--target", str(target), "--include", str(dump)],
    )
    name = f"restore_check_{now:%Y%m%d%H%M%S}"
    run("restore_test", ["createdb", name])
    try:
        run(
            "restore_test",
            ["pg_restore", "--no-owner", "--dbname", name, str(target / str(dump).lstrip("/"))],
        )
        output = run(
            "restore_test",
            [
                "psql",
                "--dbname",
                name,
                "-v",
                "ON_ERROR_STOP=1",
                "--tuples-only",
                "--no-align",
                "--command",
                RESTORE_CHECK_SQL,
            ],
        )
        users = int(output.split()[0])
        if users < 1:
            raise BackupError("restore_test", "The restored database has no users.")
    finally:
        subprocess.run(["dropdb", "--if-exists", name], capture_output=True, env=postgres_env())


def _fail(record: BackupRun, step: str, message: str) -> None:
    _finish(record, ok=False, step=step, message=message)
    logger.error("Backup failed at %s: %s", step, message)
    try:
        mail_admins(f"Backup failed: {step}", message)
    except Exception:
        logger.exception("Couldn't email ADMINS about the failed backup.")


def _finish(record: BackupRun, *, ok: bool, step: str, message: str = "") -> None:
    record.ok = ok
    record.step = step
    record.message = message[:MESSAGE_LIMIT]
    record.finished_at = timezone.now()
    record.save()
