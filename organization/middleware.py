from zoneinfo import ZoneInfo

from django.utils import timezone

from organization.models import SiteSettings


class SiteTimezoneMiddleware:
    """Render dates and times in the organization's time zone."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        timezone.activate(ZoneInfo(SiteSettings.load().time_zone))
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()
