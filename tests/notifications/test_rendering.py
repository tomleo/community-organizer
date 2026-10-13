import re

import pytest
from django.conf import settings

from notifications import messages
from notifications.calendar import shift_ics
from notifications.models import OutgoingEmail
from notifications.render import absolute_url
from organization.models import SiteSettings
from registrations.models import Registration

pytestmark = pytest.mark.django_db

TAG = re.compile(r"<[a-zA-Z/][^>]*>")


@pytest.fixture
def registration(volunteer, make_position):
    site_settings = SiteSettings.load()
    site_settings.org_name = "Neighborhood Pantry"
    site_settings.contact_email = "help@pantry.example"
    site_settings.save()
    position = make_position(title="Sorting")
    position.description = "<div>Bring <strong>gloves</strong> &amp; water</div>"
    position.save()
    event = position.event
    event.title = "Food & Fun"
    event.save()
    return Registration.objects.create(volunteer=volunteer, position=position, status="registered")


def every_kind(registration):
    position = registration.position
    messages.registered(registration)
    messages.waitlisted(registration, 3)
    messages.offered(registration)
    messages.auto_registered(registration)
    messages.offer_expired(registration)
    messages.cancelled(registration)
    messages.removed(registration, held_spot=True)
    messages.event_cancelled(position.event)
    messages.event_reinstated(position.event)
    messages.position_changed(position, "Mon, Jan 1, 2029 · 9:00 AM – 10:00 AM", "Old Hall")
    messages.reminder(registration)
    digest = {"activity": [], "underfilled": [{"position": position, "open": 2}]}
    messages.staff_digest(registration.volunteer, digest, "2026-10-10")
    from notifications.models import Message

    message = Message.objects.create(
        subject="Note & update", body="Line <1>\nLine 2", audience="Test"
    )
    messages.group_message(message, registration.volunteer)


def test_every_kind_renders(registration):
    every_kind(registration)
    kinds = set(OutgoingEmail.objects.values_list("kind", flat=True))
    assert kinds == set(OutgoingEmail.Kind.values)
    for email in OutgoingEmail.objects.all():
        assert email.subject and "\n" not in email.subject
        assert "&amp;" not in email.subject, email.kind
        assert "Neighborhood Pantry" in email.html_body
        assert "Neighborhood Pantry" in email.text_body
        assert not TAG.search(email.text_body), email.kind
        assert "&amp;" not in email.text_body and "&lt;" not in email.text_body, email.kind
        assert settings.SITE_URL in email.text_body, email.kind


def test_plain_text_description_and_title(registration):
    messages.registered(registration)
    email = OutgoingEmail.objects.get()
    assert "Food & Fun" in email.text_body
    assert "Bring gloves & water" in email.text_body
    assert "Food &amp; Fun" in email.html_body


def test_waitlist_place_and_offer_deadline(registration):
    messages.waitlisted(registration, 3)
    assert "#3" in OutgoingEmail.objects.get().text_body


def test_absolute_url():
    assert absolute_url("/events/1/") == settings.SITE_URL + "/events/1/"


def test_calendar_publish(registration):
    ics = shift_ics(registration)
    assert "METHOD:PUBLISH" in ics
    assert f"UID:registration-{registration.pk}@" in ics
    assert "SEQUENCE:0" in ics
    assert re.search(r"DTSTART:\d{8}T\d{6}Z", ics)
    assert "Sorting · Food & Fun" in ics.replace("\r\n ", "")


def test_calendar_cancel_bumps_sequence(registration):
    position = registration.position
    position.schedule_version = 2
    position.save()
    ics = shift_ics(registration, method="CANCEL")
    assert "METHOD:CANCEL" in ics
    assert "STATUS:CANCELLED" in ics
    assert "SEQUENCE:3" in ics


def test_registered_and_reminder_attach_calendar(registration):
    messages.registered(registration)
    messages.reminder(registration)
    messages.waitlisted(registration, 1)
    with_ics = dict(OutgoingEmail.objects.values_list("kind", "ics"))
    assert "METHOD:PUBLISH" in with_ics["registered"]
    assert "METHOD:PUBLISH" in with_ics["reminder"]
    assert with_ics["waitlisted"] == ""
