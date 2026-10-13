from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from notifications.models import OutgoingEmail
from notifications.tasks import send_reminders, send_staff_digests
from organization.models import SiteSettings
from registrations import services
from registrations.models import Registration

pytestmark = pytest.mark.django_db


def registered_long_ago(volunteer, position):
    registration = services.register(volunteer, position)
    Registration.objects.filter(pk=registration.pk).update(
        created_at=timezone.now() - timedelta(days=5)
    )
    OutgoingEmail.objects.all().delete()
    return registration


def test_reminder_inside_window(volunteer, make_position):
    registered_long_ago(volunteer, make_position(starts_in_hours=20))
    assert send_reminders() == 1
    assert send_reminders() == 0  # deduped
    assert OutgoingEmail.objects.filter(kind="reminder").count() == 1


def test_no_reminder_before_window_or_after_start(volunteer, make_volunteer, make_position):
    registered_long_ago(volunteer, make_position(starts_in_hours=30))
    other = make_volunteer(2)
    registration = services.register(other, make_position(starts_in_hours=40))
    Registration.objects.filter(pk=registration.pk).update(
        created_at=timezone.now() - timedelta(days=5)
    )
    from events.models import Position

    Position.objects.filter(pk=registration.position_id).update(
        starts_at=timezone.now() - timedelta(minutes=5), ends_at=timezone.now() + timedelta(hours=1)
    )
    assert send_reminders() == 0


def test_no_reminder_for_registration_made_inside_window(volunteer, make_position):
    services.register(volunteer, make_position(starts_in_hours=10))
    assert send_reminders() == 0


def test_no_reminder_when_opted_out_or_turned_off(volunteer, make_volunteer, make_position):
    volunteer.profile.reminder_emails = False
    volunteer.profile.save()
    registered_long_ago(volunteer, make_position(starts_in_hours=20))
    assert send_reminders() == 0
    registered_long_ago(make_volunteer(2), make_position(starts_in_hours=21))
    site_settings = SiteSettings.load()
    site_settings.reminder_hours_before = 0
    site_settings.save()
    assert send_reminders() == 0


def test_no_reminder_for_cancelled_event(volunteer, make_position):
    position = make_position(starts_in_hours=20)
    registered_long_ago(volunteer, position)
    position.event.cancel()
    assert send_reminders() == 0


def seven_am_today():
    site_settings = SiteSettings.load()
    site_settings.time_zone = "America/New_York"
    site_settings.save()
    local = timezone.now().astimezone(ZoneInfo("America/New_York"))
    return datetime(local.year, local.month, local.day, 7, 15, tzinfo=ZoneInfo("America/New_York"))


def test_digest_at_seven_once_and_only_opted_in(coordinator, org_admin, volunteer, make_position):
    coordinator.profile.staff_digest = True
    coordinator.profile.save()
    volunteer.profile.staff_digest = True  # not staff: ignored
    volunteer.profile.save()
    now = seven_am_today()
    position = make_position(starts_in_hours=200)
    registration = services.register(volunteer, position)
    Registration.objects.filter(pk=registration.pk).update(created_at=now - timedelta(hours=1))
    OutgoingEmail.objects.all().delete()

    assert send_staff_digests(now=now - timedelta(hours=1)) == 0  # 6 AM: not yet
    assert send_staff_digests(now=now) == 1
    assert send_staff_digests(now=now + timedelta(minutes=30)) == 0  # once per day
    email = OutgoingEmail.objects.get(kind="staff_digest")
    assert email.user == coordinator
    assert position.title in email.text_body


def test_digest_skipped_when_empty(coordinator):
    coordinator.profile.staff_digest = True
    coordinator.profile.save()
    assert send_staff_digests(now=seven_am_today()) == 0


def test_digest_lists_underfilled_soon(coordinator, make_position):
    coordinator.profile.staff_digest = True
    coordinator.profile.save()
    now = seven_am_today()
    position = make_position(slots=8, starts_in_hours=1)
    from events.models import Position

    Position.objects.filter(pk=position.pk).update(
        starts_at=now + timedelta(hours=24), ends_at=now + timedelta(hours=26)
    )
    assert send_staff_digests(now=now) == 1
    assert "8 open" in OutgoingEmail.objects.get(kind="staff_digest").text_body


def test_beat_entries():
    from django.conf import settings

    assert (
        settings.CELERY_BEAT_SCHEDULE["send-reminders"]["task"]
        == "notifications.tasks.send_reminders"
    )
    assert (
        settings.CELERY_BEAT_SCHEDULE["send-staff-digests"]["task"]
        == "notifications.tasks.send_staff_digests"
    )
