"""Production settings, checked in a fresh interpreter so module-level settings see its env."""

import json
import os
import subprocess
import sys

import pytest
from django.conf import settings as django_settings

STRONG_KEY = "a1B2c3D4e5F6g7H8i9J0" * 3
PRODUCTION = {
    "ENV_FILE": "/nonexistent/.env",
    "DJANGO_SETTINGS_MODULE": "core.settings",
    "DEBUG": "false",
    "SECRET_KEY": STRONG_KEY,
    "SITE_URL": "https://volunteer.example.org",
    "DATABASE_URL": "postgres://organizer:secret@postgres:5432/organizer",
    "EMAIL_BACKEND": "anymail.backends.postmark.EmailBackend",
    "ANYMAIL_POSTMARK_SERVER_TOKEN": "token",
    "ANYMAIL_WEBHOOK_SECRET": "webhook:secret",
}


def run(args, **overrides):
    env = {"PATH": os.environ["PATH"], **PRODUCTION, **overrides}
    env = {name: value for name, value in env.items() if value is not None}
    return subprocess.run(
        args, cwd=django_settings.BASE_DIR, env=env, capture_output=True, text=True, timeout=120
    )


def production_settings(*names, **overrides) -> dict:
    values = f"{{name: getattr(settings, name) for name in {list(names)!r}}}"
    code = (
        "import json, django; django.setup(); from django.conf import settings; "
        f"print(json.dumps({values}, default=str))"
    )
    result = run([sys.executable, "-c", code], **overrides)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_hosts_come_from_site_url():
    values = production_settings("ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS")
    assert values == {
        "ALLOWED_HOSTS": ["volunteer.example.org"],
        "CSRF_TRUSTED_ORIGINS": ["https://volunteer.example.org"],
    }


def test_hosts_can_be_set_explicitly():
    values = production_settings("ALLOWED_HOSTS", ALLOWED_HOSTS="a.example.org, b.example.org")
    assert values["ALLOWED_HOSTS"] == ["a.example.org", "b.example.org"]


def test_https_behind_proxy():
    values = production_settings(
        "SECURE_PROXY_SSL_HEADER",
        "SESSION_COOKIE_SECURE",
        "CSRF_COOKIE_SECURE",
        "SECURE_HSTS_SECONDS",
    )
    assert values == {
        "SECURE_PROXY_SSL_HEADER": ["HTTP_X_FORWARDED_PROTO", "https"],
        "SESSION_COOKIE_SECURE": True,
        "CSRF_COOKIE_SECURE": True,
        "SECURE_HSTS_SECONDS": 31536000,
    }
    assert production_settings("SECURE_HSTS_SECONDS", SECURE_HSTS_SECONDS="3600") == {
        "SECURE_HSTS_SECONDS": 3600
    }


def test_admins_version_and_paths():
    values = production_settings(
        "ADMINS",
        "SERVER_EMAIL",
        "APP_VERSION",
        "STATIC_ROOT",
        ADMINS="ops@example.org, it@example.org",
        APP_VERSION="1.2.0",
        DEFAULT_FROM_EMAIL="hello@example.org",
        STATIC_ROOT="/app/staticfiles",
    )
    assert values == {
        "ADMINS": ["ops@example.org", "it@example.org"],
        "SERVER_EMAIL": "hello@example.org",
        "APP_VERSION": "1.2.0",
        "STATIC_ROOT": "/app/staticfiles",
    }


def test_deploy_check_is_clean():
    result = run([sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"])
    assert result.returncode == 0, result.stderr + result.stdout
    assert "no issues" in result.stdout


@pytest.mark.parametrize("name", ["SECRET_KEY", "SITE_URL", "DATABASE_URL"])
def test_required_variables(name):
    result = run([sys.executable, "-c", "import django; django.setup()"], **{name: None})
    assert result.returncode != 0
    assert name in result.stderr


def test_allauth_sees_the_client_ip_behind_caddy():
    # Otherwise every visitor shares Caddy's IP and allauth's per-IP rate limits lock out everyone.
    assert production_settings("ALLAUTH_TRUSTED_PROXY_COUNT") == {"ALLAUTH_TRUSTED_PROXY_COUNT": 1}
