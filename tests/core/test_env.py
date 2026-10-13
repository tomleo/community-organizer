import pytest
from django.core.exceptions import ImproperlyConfigured

from core.env import (
    database_from_url,
    env_bool,
    env_float,
    env_int,
    env_list,
    env_str,
    google_provider_settings,
    load_dotenv,
    site_origin,
)


def test_load_dotenv_sets_missing_values_only(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('# comment\nNEW_VALUE="quoted"\nEXISTING=from-file\n\nNOT A PAIR\n')
    monkeypatch.delenv("NEW_VALUE", raising=False)
    monkeypatch.setenv("EXISTING", "from-environment")

    load_dotenv(env_file)

    import os

    assert os.environ["NEW_VALUE"] == "quoted"
    assert os.environ["EXISTING"] == "from-environment"
    monkeypatch.delenv("NEW_VALUE")


def test_load_dotenv_ignores_missing_file(tmp_path):
    load_dotenv(tmp_path / "does-not-exist")


def test_env_str_required_raises(monkeypatch):
    monkeypatch.delenv("REQUIRED_THING", raising=False)
    with pytest.raises(ImproperlyConfigured, match="REQUIRED_THING"):
        env_str("REQUIRED_THING")


def test_env_str_default_and_value(monkeypatch):
    monkeypatch.delenv("OPTIONAL_THING", raising=False)
    assert env_str("OPTIONAL_THING", "fallback") == "fallback"
    monkeypatch.setenv("OPTIONAL_THING", "set")
    assert env_str("OPTIONAL_THING", "fallback") == "set"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("1", True), ("YES", True), ("false", False), ("0", False), ("off", False)],
)
def test_env_bool_parses(monkeypatch, raw, expected):
    monkeypatch.setenv("FLAG", raw)
    assert env_bool("FLAG", not expected) is expected


def test_env_bool_rejects_garbage(monkeypatch):
    monkeypatch.setenv("FLAG", "maybe")
    with pytest.raises(ImproperlyConfigured, match="FLAG"):
        env_bool("FLAG", False)


def test_env_int_and_list(monkeypatch):
    monkeypatch.setenv("PORT_NUMBER", "2525")
    monkeypatch.setenv("HOSTS", "example.org, www.example.org ,")
    assert env_int("PORT_NUMBER", 25) == 2525
    assert env_list("HOSTS", []) == ["example.org", "www.example.org"]
    monkeypatch.delenv("HOSTS")
    assert env_list("HOSTS", ["localhost"]) == ["localhost"]


def test_database_from_url():
    config = database_from_url("postgres://user:p%40ss@db.internal:6543/organizer")
    assert config == {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "organizer",
        "USER": "user",
        "PASSWORD": "p@ss",
        "HOST": "db.internal",
        "PORT": "6543",
    }


def test_database_from_url_rejects_other_schemes():
    with pytest.raises(ImproperlyConfigured):
        database_from_url("mysql://user:pass@localhost/db")


def test_google_provider_settings_without_credentials():
    config = google_provider_settings("", "")
    assert "APP" not in config
    assert config["SCOPE"] == ["profile", "email"]


def test_google_provider_settings_with_credentials():
    config = google_provider_settings("client-id", "client-secret")
    assert config["APP"] == {"client_id": "client-id", "secret": "client-secret", "key": ""}


def test_anymail_settings_from_environment():
    from core.env import anymail_settings

    environ = {
        "ANYMAIL_POSTMARK_SERVER_TOKEN": "token",
        "ANYMAIL_WEBHOOK_SECRET": "user:pass",
        "OTHER": "ignored",
    }
    assert anymail_settings(environ) == {
        "POSTMARK_SERVER_TOKEN": "token",
        "WEBHOOK_SECRET": "user:pass",
    }


def test_site_origin():
    assert site_origin("https://volunteer.example.org/") == (
        "volunteer.example.org",
        "https://volunteer.example.org",
    )
    assert site_origin("https://localhost:8443") == ("localhost", "https://localhost:8443")
    with pytest.raises(ImproperlyConfigured, match="SITE_URL"):
        site_origin("volunteer.example.org")


def test_env_float(monkeypatch):
    monkeypatch.setenv("RATE", "0.25")
    assert env_float("RATE", 0.0) == 0.25
    monkeypatch.delenv("RATE")
    assert env_float("RATE", 0.5) == 0.5
    monkeypatch.setenv("RATE", "lots")
    with pytest.raises(ImproperlyConfigured, match="RATE"):
        env_float("RATE", 0.0)
