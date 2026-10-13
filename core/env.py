"""Read configuration from environment variables, optionally loaded from a .env file."""

import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured

_REQUIRED = object()
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines into os.environ without overriding variables that are already set."""
    if not path.is_file():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def env_str(name: str, default=_REQUIRED) -> str:
    value = os.environ.get(name, "")
    if value == "":
        if default is _REQUIRED:
            raise ImproperlyConfigured(f"Environment variable {name} is required.")
        return default
    return value


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if value == "":
        return default
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ImproperlyConfigured(f"Environment variable {name} must be a boolean, got {value!r}.")


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ImproperlyConfigured(f"Environment variable {name} must be an integer.") from exc


def env_list(name: str, default: list[str]) -> list[str]:
    value = os.environ.get(name, "")
    if value.strip() == "":
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def database_from_url(url: str) -> dict:
    parts = urlsplit(url)
    if parts.scheme not in {"postgres", "postgresql"}:
        raise ImproperlyConfigured("DATABASE_URL must be a postgres:// URL.")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parts.path.lstrip("/")),
        "USER": unquote(parts.username or ""),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname or "",
        "PORT": str(parts.port or ""),
    }


def google_provider_settings(client_id: str, client_secret: str) -> dict:
    """allauth provider config for Google; the provider is only offered when credentials exist."""
    config = {"SCOPE": ["profile", "email"], "AUTH_PARAMS": {"access_type": "online"}}
    if client_id and client_secret:
        config["APP"] = {"client_id": client_id, "secret": client_secret, "key": ""}
    return config


def anymail_settings(environ) -> dict:
    """Every ANYMAIL_<NAME> environment variable becomes ANYMAIL["<NAME>"] (provider-agnostic)."""
    prefix = "ANYMAIL_"
    return {key[len(prefix) :]: value for key, value in environ.items() if key.startswith(prefix)}


def check_anymail_webhook_secret(email_backend: str, debug: bool, anymail: dict) -> None:
    """Without a secret, anyone could post fake bounces and stop a volunteer's emails."""
    if email_backend.startswith("anymail.") and not debug and not anymail.get("WEBHOOK_SECRET"):
        raise ImproperlyConfigured(
            "Set ANYMAIL_WEBHOOK_SECRET to protect the delivery-tracking webhook."
        )


def template_dirs(custom_dir: str, default: Path) -> list[Path]:
    """CUSTOM_TEMPLATES_DIR (if set) is searched before the app's own templates."""
    return [Path(custom_dir), default] if custom_dir else [default]


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name, "").strip()
    if value == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ImproperlyConfigured(f"Environment variable {name} must be a number.") from exc


def site_origin(site_url: str) -> tuple[str, str]:
    """(host, origin) of SITE_URL, e.g. ("volunteer.example.org", "https://volunteer.example.org")."""
    parts = urlsplit(site_url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ImproperlyConfigured(
            "SITE_URL must be an absolute URL such as https://volunteer.example.org."
        )
    return parts.hostname, f"{parts.scheme}://{parts.netloc}"
