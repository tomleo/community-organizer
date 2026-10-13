from contextlib import contextmanager
from zoneinfo import ZoneInfo

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from core.images import variant_url
from organization.models import SiteSettings


def absolute_url(path: str) -> str:
    return f"{settings.SITE_URL}{path}"


@contextmanager
def site_timezone():
    """Activate the organization's time zone (Celery and beat have no middleware to do it)."""
    with timezone.override(ZoneInfo(SiteSettings.load().time_zone)):
        yield


def render_email(kind: str, context: dict) -> tuple[str, str, str]:
    """Render subject, text and HTML for `templates/emails/<kind>/` in the site time zone."""
    site_settings = SiteSettings.load()
    context = {
        "site_settings": site_settings,
        "site_url": settings.SITE_URL,
        "logo_url": absolute_url(variant_url(site_settings.logo, 128))
        if site_settings.logo
        else "",
        **context,
    }
    with site_timezone():
        subject = render_to_string(f"emails/{kind}/subject.txt", context)
        text = render_to_string(f"emails/{kind}/body.txt", context)
        html = render_to_string(f"emails/{kind}/body.html", context)
    return " ".join(subject.split()), text.strip() + "\n", html
