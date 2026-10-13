"""Django settings for Community Organizer. Configuration comes from environment variables."""

import os
from pathlib import Path

from celery.schedules import crontab

from core.env import (
    anymail_settings,
    check_anymail_webhook_secret,
    database_from_url,
    env_bool,
    env_float,
    env_int,
    env_list,
    env_str,
    google_provider_settings,
    load_dotenv,
    site_origin,
    template_dirs,
)
from core.sentry import init_sentry

BASE_DIR = Path(__file__).resolve().parent.parent
# Containers get their environment from docker compose; ENV_FILE lets tests point elsewhere.
load_dotenv(Path(os.environ.get("ENV_FILE", BASE_DIR / ".env")))

DEBUG = env_bool("DEBUG", False)
SECRET_KEY = env_str("SECRET_KEY")
# Absolute base URL for links in emails (Celery tasks have no request to build them from).
SITE_URL = (env_str("SITE_URL", "http://localhost:9000") if DEBUG else env_str("SITE_URL")).rstrip(
    "/"
)
_site_host, _site_origin = site_origin(SITE_URL)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", ["localhost", "127.0.0.1"] if DEBUG else [_site_host])
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", [] if DEBUG else [_site_origin])
APP_VERSION = env_str("APP_VERSION", "dev")

if not DEBUG:
    # Caddy terminates HTTPS and forwards X-Forwarded-Proto.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
    # Caddy sets X-Forwarded-For to the visitor's address; allauth rate-limits per visitor IP.
    ALLAUTH_TRUSTED_PROXY_COUNT = 1

SILENCED_SYSTEM_CHECKS = [
    # Caddy redirects HTTP to HTTPS; the container healthcheck reaches Django over plain HTTP.
    "security.W008",
    # HSTS preloading is a commitment for the domain's owner to make, not an app default.
    "security.W021",
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "organization",
    "accounts",
    "events",
    "registrations",
    "anymail",
    "notifications",
    "volunteers",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
]

MIDDLEWARE = [
    "core.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "organization.middleware.SiteTimezoneMiddleware",
    "accounts.middleware.OnboardingMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": template_dirs(env_str("CUSTOM_TEMPLATES_DIR", ""), BASE_DIR / "templates"),
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "organization.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

DATABASES = {"default": database_from_url(env_str("DATABASE_URL"))}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = Path(env_str("STATIC_ROOT", str(BASE_DIR / "staticfiles")))
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env_str("MEDIA_ROOT", str(BASE_DIR / "media")))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
            if env_bool("STATIC_MANIFEST", not DEBUG)
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}

IMAGE_UPLOAD_MAX_BYTES = 10 * 1024 * 1024
# Pixel caps guard against decompression bombs and keep resizing within the worker's memory budget.
IMAGE_MAX_PIXELS = 16_000_000  # PNG and WebP
IMAGE_MAX_PIXELS_JPEG = 50_000_000  # covers 48–50 MP phone photos

DEFAULT_FROM_EMAIL = env_str("DEFAULT_FROM_EMAIL", "organizer@localhost")
SERVER_EMAIL = env_str("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
ADMINS = env_list("ADMINS", [])  # receive 500-error and backup-failure emails
_email_backend = env_str("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
MAILERS = {"default": {"BACKEND": _email_backend}}
if _email_backend == "django.core.mail.backends.smtp.EmailBackend":
    MAILERS["default"]["OPTIONS"] = {
        "host": env_str("EMAIL_HOST"),
        "port": env_int("EMAIL_PORT", 587),
        "username": env_str("EMAIL_HOST_USER", ""),
        "password": env_str("EMAIL_HOST_PASSWORD", ""),
        "use_tls": env_bool("EMAIL_USE_TLS", True),
    }

ANYMAIL = anymail_settings(os.environ)
check_anymail_webhook_secret(_email_backend, DEBUG, ANYMAIL)


# Cache and broker use separate Valkey databases: cache.clear() flushes its whole database.
VALKEY_CACHE_URL = env_str("VALKEY_CACHE_URL", "redis://localhost:6379/1")
VALKEY_BROKER_URL = env_str("VALKEY_BROKER_URL", "redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": VALKEY_CACHE_URL,
        "KEY_PREFIX": "organizer",
    }
}

CELERY_BROKER_URL = VALKEY_BROKER_URL
CELERY_RESULT_BACKEND = VALKEY_BROKER_URL
CELERY_TASK_IGNORE_RESULT = True
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "expire-waitlist-offers": {
        "task": "registrations.tasks.expire_offers",
        "schedule": 300,  # seconds
    },
    "resend-stuck-emails": {
        "task": "notifications.tasks.resend_stuck",
        "schedule": 600,
    },
    "send-reminders": {
        "task": "notifications.tasks.send_reminders",
        "schedule": crontab(minute=0),
    },
    "send-staff-digests": {
        "task": "notifications.tasks.send_staff_digests",
        "schedule": crontab(minute=0),
    },
}

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LOGIN_REDIRECT_URL = "home"
ACCOUNT_LOGOUT_REDIRECT_URL = "home"
ACCOUNT_ADAPTER = "accounts.adapters.AccountAdapter"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = True
ACCOUNT_PASSWORD_RESET_BY_CODE_ENABLED = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True

SOCIALACCOUNT_PROVIDERS = {
    "google": google_provider_settings(
        env_str("GOOGLE_CLIENT_ID", ""), env_str("GOOGLE_CLIENT_SECRET", "")
    ),
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
        "mail_admins": {"class": "core.log.AdminEmailHandler", "level": "ERROR"},
    },
    "root": {"handlers": ["console"], "level": env_str("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.request": {
            "handlers": ["console", "mail_admins"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

# Backups (core/backups.py): nightly at BACKUP_TIME in the site time zone.
BACKUP_TIME = env_str("BACKUP_TIME", "03:00")
BACKUP_WORK_DIR = Path(env_str("BACKUP_WORK_DIR", "/tmp/organizer-backup"))
BACKUP_HEALTH_URL = env_str("BACKUP_HEALTH_URL", "http://web:8000/health/")

init_sentry(
    env_str("SENTRY_DSN", ""),
    release=APP_VERSION,
    environment=env_str("SENTRY_ENVIRONMENT", "production"),
    traces_sample_rate=env_float("SENTRY_TRACES_SAMPLE_RATE", 0.0),
)
