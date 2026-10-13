"""Stand-ins for restic and the PostgreSQL client tools, so backup tests run without them."""

import json
import os
import sys
from pathlib import Path

TOOLS = ["restic", "pg_dump", "pg_restore", "psql", "createdb", "dropdb"]

STUB = """#!{python}
import json, os, sys
from pathlib import Path

name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps([name, *args]) + "\\n")
command = " ".join([name, *args])
fail = os.environ.get("STUB_FAIL", "")
if fail and command.startswith(fail):
    print("stub failure: " + command, file=sys.stderr)
    sys.exit(1)


def value(flag):
    return args[args.index(flag) + 1]


if name == "restic":
    if args[:2] == ["cat", "config"]:
        sys.exit(int(os.environ.get("STUB_CAT_CONFIG_EXIT", "0")))
    if args[0] == "backup":
        print(json.dumps({{"message_type": "status", "percent_done": 1}}))
        print(json.dumps({{"message_type": "summary", "snapshot_id": "abc123def456"}}))
    if args[0] == "snapshots":
        default = [{{"short_id": "abc123de", "time": "2026-10-11T07:00:05Z"}}]
        print(os.environ.get("STUB_SNAPSHOTS", json.dumps(default)))
    if args[0] == "restore":
        target = Path(value("--target"))
        for source in os.environ.get("STUB_SNAPSHOT_FILES", "").split(os.pathsep):
            if source:
                restored = target / source.lstrip("/")
                restored.parent.mkdir(parents=True, exist_ok=True)
                restored.write_text("restored " + source)
if name == "pg_dump":
    Path(value("--file")).write_bytes(b"PGDMP")
if name == "psql":
    print(os.environ.get("STUB_PSQL_OUTPUT", "3\\n1\\n0"))
"""


class BackupTools:
    def __init__(self, root: Path, monkeypatch, settings):
        self.bin = root / "bin"
        self.bin.mkdir()
        self.log = root / "calls.jsonl"
        self.work = root / "work"
        for tool in TOOLS:
            path = self.bin / tool
            path.write_text(STUB.format(python=sys.executable))
            path.chmod(0o755)
        self._monkeypatch = monkeypatch
        monkeypatch.setenv("PATH", f"{self.bin}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("STUB_LOG", str(self.log))
        monkeypatch.setenv("RESTIC_REPOSITORY", "s3:https://backups.example.org/bucket")
        monkeypatch.setenv("RESTIC_PASSWORD", "test-password")
        settings.BACKUP_WORK_DIR = self.work

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def commands(self) -> list[str]:
        """First two words of each call, e.g. "restic backup"."""
        return [" ".join(call[:2]) for call in self.calls()]

    def fail(self, prefix: str) -> None:
        self._monkeypatch.setenv("STUB_FAIL", prefix)

    def set(self, name: str, value: str) -> None:
        self._monkeypatch.setenv(name, value)
