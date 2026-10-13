"""Container health check, answered before other middleware touches sessions or the database."""

import logging

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)

HEALTH_PATH = "/health/"


def _database_ok() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return True


def _cache_ok() -> bool:
    cache.set("health-check", "ok", timeout=10)
    return cache.get("health-check") == "ok"


CHECKS = [("database", _database_ok), ("cache", _cache_ok)]


def _failed_checks() -> list[str]:
    failed = []
    for name, check in CHECKS:
        try:
            ok = check()
        except Exception:
            logger.warning("Health check: %s failed", name, exc_info=True)
            ok = False
        if not ok:
            failed.append(name)
    return failed


class HealthCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info != HEALTH_PATH:
            return self.get_response(request)
        failed = _failed_checks()
        if failed:
            response = JsonResponse({"status": "error", "failed": failed}, status=503)
        else:
            response = JsonResponse({"status": "ok", "version": settings.APP_VERSION})
        response["Cache-Control"] = "no-store"
        return response
