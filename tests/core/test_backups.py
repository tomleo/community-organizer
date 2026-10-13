from datetime import UTC, datetime, timedelta

import pytest
from django.urls import reverse

from core.backups import backup_once, backup_status
from organization.models import BackupRun, SiteSettings

pytestmark = pytest.mark.django_db

SATURDAY = datetime(2026, 10, 10, 3, 0, tzinfo=UTC)
SUNDAY = datetime(2026, 10, 11, 3, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def admins(settings):
    settings.ADMINS = ["ops@example.org"]


def set_time_zone(name):
    site_settings = SiteSettings.load()
    site_settings.time_zone = name
    site_settings.save()


def test_success(backup_tools):
    run = backup_once(BackupRun.Kind.NIGHTLY, now=SATURDAY)
    assert run.ok is True
    assert run.step == "prune"
    assert run.snapshot_id == "abc123def456"
    assert run.finished_at is not None
    assert backup_tools.commands() == [
        "restic cat",
        "pg_dump --format=custom",
        "restic backup",
        "restic forget",
    ]
    backup_call = next(call for call in backup_tools.calls() if call[:2] == ["restic", "backup"])
    assert "--tag" in backup_call and "nightly" in backup_call
    forget_call = next(call for call in backup_tools.calls() if call[:2] == ["restic", "forget"])
    assert forget_call[2:] == [
        "--prune",
        "--keep-daily",
        "7",
        "--keep-weekly",
        "4",
        "--keep-monthly",
        "12",
    ]
    assert not backup_tools.work.exists()


def test_repository_initialized_when_missing(backup_tools):
    backup_tools.set("STUB_CAT_CONFIG_EXIT", "10")
    assert backup_once(BackupRun.Kind.NIGHTLY, now=SATURDAY).ok is True
    assert backup_tools.commands()[:2] == ["restic cat", "restic init"]


def test_unreadable_repository_fails(backup_tools):
    backup_tools.set("STUB_CAT_CONFIG_EXIT", "1")
    run = backup_once(BackupRun.Kind.NIGHTLY, now=SATURDAY)
    assert (run.ok, run.step) == (False, "upload")


@pytest.mark.parametrize(
    "command, step",
    [
        ("pg_dump", "dump"),
        ("restic backup", "upload"),
        ("restic forget", "prune"),
        ("restic check", "check"),
        ("createdb", "restore_test"),
        ("pg_restore", "restore_test"),
    ],
)
def test_failures_are_recorded_and_emailed(backup_tools, mailoutbox, command, step):
    backup_tools.fail(command)
    run = backup_once(BackupRun.Kind.NIGHTLY, now=SUNDAY)
    assert (run.ok, run.step) == (False, step)
    assert "stub failure" in run.message
    assert run.finished_at is not None
    assert len(mailoutbox) == 1
    assert f"Backup failed: {step}" in mailoutbox[0].subject
    assert not backup_tools.work.exists()


def test_unexpected_errors_are_recorded_and_emailed(backup_tools, mailoutbox, monkeypatch):
    def broken(dump, kind):
        raise FileNotFoundError("restic: command not found")

    monkeypatch.setattr("core.backups._upload", broken)
    run = backup_once(BackupRun.Kind.NIGHTLY, now=SATURDAY)
    assert (run.ok, run.step) == (False, "upload")
    assert "command not found" in run.message
    assert run.finished_at is not None
    assert len(mailoutbox) == 1
    assert not backup_tools.work.exists()


def test_sunday_checks_and_restore_test(backup_tools):
    run = backup_once(BackupRun.Kind.NIGHTLY, now=SUNDAY)
    assert (run.ok, run.step) == (True, "restore_test")
    commands = backup_tools.commands()
    assert commands[4:] == [
        "restic check",
        "restic restore",
        "createdb restore_check_20261011030000",
        "pg_restore --no-owner",
        "psql --dbname",
        "dropdb --if-exists",
    ]
    dropped = backup_tools.calls()[-1]
    assert dropped[-1] == "restore_check_20261011030000"


def test_restore_test_needs_users_and_cleans_up(backup_tools):
    backup_tools.set("STUB_PSQL_OUTPUT", "0\n0\n0")
    run = backup_once(BackupRun.Kind.NIGHTLY, now=SUNDAY)
    assert (run.ok, run.step) == (False, "restore_test")
    assert backup_tools.commands()[-1] == "dropdb --if-exists"
    assert not backup_tools.work.exists()


def test_sunday_is_the_sites_sunday(backup_tools):
    set_time_zone("Pacific/Auckland")
    # Saturday 14:00 UTC is Sunday 03:00 in Auckland.
    run = backup_once(BackupRun.Kind.NIGHTLY, now=datetime(2026, 10, 10, 14, 0, tzinfo=UTC))
    assert run.step == "restore_test"
    assert "restic check" in backup_tools.commands()


def test_manual_runs_skip_weekly_checks(backup_tools):
    run = backup_once(BackupRun.Kind.MANUAL, now=SUNDAY)
    assert run.step == "prune"
    assert "restic check" not in backup_tools.commands()


def test_missing_media_folder_is_created(backup_tools, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "no-media-yet"
    assert backup_once(BackupRun.Kind.NIGHTLY, now=SATURDAY).ok is True


def test_not_configured_is_recorded_once_a_day(backup_tools, monkeypatch):
    monkeypatch.delenv("RESTIC_REPOSITORY")
    backup_once(BackupRun.Kind.NIGHTLY, now=SATURDAY)
    backup_once(BackupRun.Kind.NIGHTLY, now=SATURDAY + timedelta(hours=1))
    assert list(BackupRun.objects.values_list("ok", "step")) == [(False, "not_configured")]
    backup_once(BackupRun.Kind.NIGHTLY, now=SATURDAY + timedelta(days=1))
    assert BackupRun.objects.count() == 2
    assert backup_tools.calls() == []


def test_old_runs_are_pruned(backup_tools):
    BackupRun.objects.create(kind="nightly", ok=True, started_at=SATURDAY - timedelta(days=91))
    kept = BackupRun.objects.create(
        kind="nightly", ok=True, started_at=SATURDAY - timedelta(days=89)
    )
    run = backup_once(BackupRun.Kind.NIGHTLY, now=SATURDAY)
    assert set(BackupRun.objects.all()) == {kept, run}


def finished(started_at, ok=True, step="prune"):
    return BackupRun.objects.create(
        kind="nightly", ok=ok, step=step, started_at=started_at, finished_at=started_at
    )


def test_status(backup_tools, monkeypatch):
    now = SATURDAY
    status = backup_status(now)
    assert status["warning"] and "No backup has run yet" in status["text"]

    finished(now - timedelta(hours=3))
    status = backup_status(now)
    assert status == {"warning": False, "text": "", "last_ok": now - timedelta(hours=3)}

    finished(now - timedelta(hours=1), ok=False, step="upload")
    status = backup_status(now)
    assert status["warning"] and "failed" in status["text"]

    BackupRun.objects.all().delete()
    finished(now - timedelta(days=3))
    status = backup_status(now)
    assert status["warning"] and "2 days" in status["text"]

    BackupRun.objects.all().delete()
    BackupRun.objects.create(
        kind="nightly", step="not_configured", started_at=now - timedelta(hours=2), finished_at=now
    )
    status = backup_status(now)
    assert status["warning"] and "not configured" in status["text"]


def test_status_comes_from_recorded_runs(backup_tools, monkeypatch):
    # Only the backup service has the restic credentials; the web app reads its records.
    monkeypatch.delenv("RESTIC_REPOSITORY")
    finished(SATURDAY - timedelta(hours=3))
    assert backup_status(SATURDAY)["warning"] is False


def test_settings_page_shows_status(client, org_admin, backup_tools):
    finished(SATURDAY)
    client.force_login(org_admin)
    content = client.get(reverse("manage_settings")).content.decode()
    assert "Last successful backup" in content


def test_snapshots_share_one_host_name(backup_tools):
    # Containers get random host names; restic applies retention per host, so pin one.
    backup_once(BackupRun.Kind.NIGHTLY, now=SATURDAY)
    backup_call = next(call for call in backup_tools.calls() if call[:2] == ["restic", "backup"])
    assert backup_call[backup_call.index("--host") + 1] == "community-organizer"
