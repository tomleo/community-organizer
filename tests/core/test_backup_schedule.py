from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import CommandError, call_command

from core import backups
from core.backups import next_run, parse_backup_time

NEW_YORK = ZoneInfo("America/New_York")


def test_parse_backup_time():
    assert parse_backup_time("03:00") == time(3, 0)
    with pytest.raises(ImproperlyConfigured, match="BACKUP_TIME"):
        parse_backup_time("3am")


def test_later_today():
    now = datetime(2026, 10, 12, 6, 0, tzinfo=UTC)  # 02:00 in New York
    assert next_run(now, time(3, 0), NEW_YORK) == datetime(2026, 10, 12, 7, 0, tzinfo=UTC)


def test_tomorrow_once_passed():
    now = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)  # 04:00 in New York
    assert next_run(now, time(3, 0), NEW_YORK) == datetime(2026, 10, 13, 7, 0, tzinfo=UTC)


def test_across_fall_back():
    now = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)  # DST ends Nov 1
    assert next_run(now, time(3, 0), NEW_YORK) == datetime(2026, 11, 1, 8, 0, tzinfo=UTC)


def test_across_spring_forward():
    now = datetime(2026, 3, 7, 12, 0, tzinfo=UTC)  # DST starts Mar 8
    assert next_run(now, time(3, 0), NEW_YORK) == datetime(2026, 3, 8, 7, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, start):
        self.current = start
        self.sleeps = []

    def now(self):
        return self.current

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.current += timedelta(seconds=seconds)


@pytest.mark.django_db(transaction=True)  # the loop closes old connections
def test_run_forever_sleeps_until_due(monkeypatch, settings):
    settings.BACKUP_TIME = "03:00"
    clock = FakeClock(datetime(2026, 10, 12, 1, 30, tzinfo=UTC))  # site time zone is UTC
    runs = []
    monkeypatch.setattr(
        backups, "backup_once", lambda kind, now=None, echo=None: runs.append((kind, now))
    )
    backups.run_forever(sleep=clock.sleep, clock=clock.now, max_runs=1)
    assert runs == [("nightly", datetime(2026, 10, 12, 3, 0, tzinfo=UTC))]
    assert max(clock.sleeps) <= backups.WAKE_INTERVAL


@pytest.mark.django_db(transaction=True)  # the loop closes old connections
def test_run_forever_survives_errors(monkeypatch, caplog):
    clock = FakeClock(datetime(2026, 10, 12, 2, 59, tzinfo=UTC))
    attempts = []

    def crash(kind, now=None, echo=None):
        attempts.append(now)
        raise RuntimeError("database restarting")

    monkeypatch.setattr(backups, "backup_once", crash)
    backups.run_forever(sleep=clock.sleep, clock=clock.now, max_runs=2)
    assert attempts == [
        datetime(2026, 10, 12, 3, 0, tzinfo=UTC),
        datetime(2026, 10, 13, 3, 0, tzinfo=UTC),
    ]
    assert "database restarting" in caplog.text


@pytest.mark.django_db
def test_backup_now(backup_tools, capsys):
    call_command("backup_now")
    out = capsys.readouterr().out
    assert "Dumping the database" in out and "Backup finished" in out
    assert backups.BackupRun.objects.get().kind == "manual"


@pytest.mark.django_db
def test_backup_now_failure(backup_tools):
    backup_tools.fail("restic backup")
    with pytest.raises(CommandError, match="upload"):
        call_command("backup_now")


@pytest.mark.django_db
def test_backup_now_not_configured(backup_tools, monkeypatch):
    monkeypatch.delenv("RESTIC_REPOSITORY")
    with pytest.raises(CommandError, match="RESTIC_REPOSITORY"):
        call_command("backup_now")
