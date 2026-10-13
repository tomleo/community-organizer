import os
import socket
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from django.core.management import CommandError, call_command

pytestmark = pytest.mark.django_db

DOMAIN = "volunteer.example.org"


@contextmanager
def health_server(status):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/health/"
    finally:
        server.shutdown()
        server.server_close()


def unused_url():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{sock.getsockname()[1]}/health/"


@pytest.fixture
def site(settings, backup_tools, tmp_path):
    settings.SITE_URL = f"https://{DOMAIN}"
    settings.BACKUP_HEALTH_URL = unused_url()
    media = tmp_path / "media"
    (media / "events").mkdir(parents=True)
    (media / "events" / "old.jpg").write_text("old")
    settings.MEDIA_ROOT = media
    backup_tools.set(
        "STUB_SNAPSHOT_FILES",
        os.pathsep.join(
            [str(backup_tools.work / "database.dump"), str(media / "events" / "new.jpg")]
        ),
    )
    return media


@pytest.mark.parametrize("status", [200, 503])
def test_refuses_while_site_answers(site, settings, backup_tools, status):
    with health_server(status) as url:
        settings.BACKUP_HEALTH_URL = url
        with pytest.raises(CommandError, match="docker compose stop web worker beat"):
            call_command("restore_backup", "latest", yes_i_am_sure=DOMAIN)
    assert "restic restore" not in backup_tools.commands()


def test_refuses_wrong_domain(site, backup_tools):
    with pytest.raises(CommandError, match="didn't match"):
        call_command("restore_backup", "latest", yes_i_am_sure="other.example.org")
    assert "restic restore" not in backup_tools.commands()
    assert (site / "events" / "old.jpg").exists()


def test_asks_for_the_domain(site, monkeypatch, backup_tools, capsys):
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or DOMAIN)
    call_command("restore_backup")
    assert DOMAIN in prompts[0]
    assert "2026-10-11" in capsys.readouterr().out


def test_restores_database_and_media(site, backup_tools, capsys):
    call_command("restore_backup", "abc123de", yes_i_am_sure=DOMAIN)
    restore_call = next(call for call in backup_tools.calls() if call[:2] == ["restic", "restore"])
    assert restore_call[2] == "abc123de"
    # Start from an empty schema, so a backup made before newer migrations restores cleanly.
    names = [call[0] for call in backup_tools.calls()]
    reset = next(call for call in backup_tools.calls() if call[0] == "psql")
    assert "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" in reset
    assert names.index("psql") < names.index("pg_restore")
    pg_restore = next(call for call in backup_tools.calls() if call[0] == "pg_restore")
    assert pg_restore[1:4] == ["--no-owner", "--single-transaction", "--exit-on-error"]
    assert pg_restore[-1].endswith("database.dump")
    assert (site / "events" / "new.jpg").exists()
    assert not (site / "events" / "old.jpg").exists()
    assert not backup_tools.work.exists()
    assert "Restored" in capsys.readouterr().out


def test_database_failure_leaves_media_alone(site, backup_tools):
    backup_tools.fail("pg_restore")
    with pytest.raises(CommandError, match="stub failure"):
        call_command("restore_backup", yes_i_am_sure=DOMAIN)
    assert (site / "events" / "old.jpg").exists()
    assert not backup_tools.work.exists()


def test_unknown_snapshot(site, backup_tools):
    backup_tools.set("STUB_SNAPSHOTS", "[]")
    with pytest.raises(CommandError, match="No snapshot"):
        call_command("restore_backup", "nope", yes_i_am_sure=DOMAIN)
