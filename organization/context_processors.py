from django.conf import settings

from organization.models import SiteSettings
from organization.permissions import management_links


def site(request):
    links = management_links(request.user)
    return {
        "site_settings": SiteSettings.load(),
        "app_version": settings.APP_VERSION,
        "management_links": links,
        "can_manage": bool(links),
        "email_problem": _email_problem(request.user),
    }


def _email_problem(user) -> str:
    if not user.is_authenticated:
        return ""
    profile = getattr(user, "profile", None)
    if profile is None or profile.email_undeliverable_at is None:
        return ""
    return profile.email_undeliverable_reason or "Email to your address could not be delivered"
