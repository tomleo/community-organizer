import os
import subprocess

from django.conf import settings

SCRIPT = settings.BASE_DIR / "scripts" / "release.sh"


def release(*args, **env):
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        env={"PATH": os.environ["PATH"], **env},
        capture_output=True,
        text=True,
        cwd=settings.BASE_DIR,
    )


def test_needs_a_version():
    result = release()
    assert result.returncode != 0 and "Usage" in result.stderr


def test_rejects_malformed_version():
    result = release("1.2", IMAGE="ghcr.io/example/community-organizer")
    assert result.returncode != 0 and "1.2.3" in result.stderr


def test_needs_image():
    result = release("1.2.0")
    assert result.returncode != 0 and "IMAGE" in result.stderr
