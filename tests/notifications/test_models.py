import pytest
from django.conf import settings
from django.contrib.auth.models import Group

from notifications.models import OutgoingEmail
from organization.models import SiteSettings

pytestmark = pytest.mark.django_db


def test_site_url_has_no_trailing_slash():
    assert settings.SITE_URL and not settings.SITE_URL.endswith("/")


def test_status_moves_forward_only():
    email = OutgoingEmail(status="sent")
    assert email.can_move_to("delivered")
    assert email.can_move_to("bounced")
    email.status = "bounced"
    assert not email.can_move_to("delivered")
    email.status = "delivered"
    assert email.can_move_to("complained")
    assert not email.can_move_to("sent")


def test_profile_notification_defaults(volunteer):
    profile = volunteer.profile
    assert profile.reminder_emails is True
    assert profile.staff_digest is False
    assert profile.email_undeliverable_at is None
    assert profile.email_undeliverable_reason == ""


def test_position_schedule_version_default(make_position):
    assert make_position().schedule_version == 0


def test_reminder_setting_default():
    assert SiteSettings.load().reminder_hours_before == 24


def test_admin_can_view_email_log_coordinator_cannot():
    admin = set(Group.objects.get(name="Admin").permissions.values_list("codename", flat=True))
    coordinator = set(
        Group.objects.get(name="Coordinator").permissions.values_list("codename", flat=True)
    )
    assert "view_outgoingemail" in admin
    assert "view_outgoingemail" not in coordinator


def test_anymail_urls_mounted():
    from django.urls import resolve

    assert resolve("/anymail/postmark/tracking/").url_name == "postmark_tracking_webhook"
