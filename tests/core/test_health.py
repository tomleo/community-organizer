import pytest
from django.db import OperationalError, connection
from django.urls import reverse

pytestmark = pytest.mark.django_db

BROKEN_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://127.0.0.1:1/1",
    }
}


def broken(*args, **kwargs):
    raise OperationalError("database is down")


def test_ok(client, settings):
    settings.APP_VERSION = "1.2.0"
    response = client.get("/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.2.0"}
    assert response["Cache-Control"] == "no-store"


def test_any_host(client):
    # The container healthcheck doesn't know the public host name.
    assert client.get("/health/", HTTP_HOST="web:8000").status_code == 200


def test_database_down(client, monkeypatch):
    monkeypatch.setattr(connection, "cursor", broken)
    response = client.get("/health/")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "failed": ["database"]}


def test_cache_down(client, settings):
    settings.CACHES = BROKEN_CACHE
    response = client.get("/health/")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "failed": ["cache"]}


def test_both_down(client, settings, monkeypatch):
    settings.CACHES = BROKEN_CACHE
    monkeypatch.setattr(connection, "cursor", broken)
    assert client.get("/health/").json()["failed"] == ["database", "cache"]


def test_logged_in_volunteer_with_missing_profile_still_gets_health(client, make_user):
    client.force_login(make_user("incomplete@example.org"))
    assert client.get("/health/").status_code == 200


def test_staff_footer_shows_version(client, settings, coordinator, volunteer):
    settings.APP_VERSION = "1.2.0"
    client.force_login(coordinator)
    assert "Version 1.2.0" in client.get(reverse("home")).content.decode()
    client.force_login(volunteer)
    assert "Version 1.2.0" not in client.get(reverse("home")).content.decode()
