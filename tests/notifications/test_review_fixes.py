import re
from datetime import UTC, datetime, timedelta

import pytest
from anymail.exceptions import AnymailAPIError
from anymail.signals import AnymailTrackingEvent, tracking
from celery.exceptions import Retry
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from django.utils import timezone

from events.models import Position
from notifications import messages, outbox
from notifications.models import OutgoingEmail
from notifications.tasks import resend_stuck, send_outgoing
from organization.models import SiteSettings
from registrations import services

pytestmark = pytest.mark.django_db


# Times in emails built outside a request (Celery, beat) use the site time zone.


def test_email_times_use_site_time_zone_outside_requests(volunteer, make_position):
    site_settings = SiteSettings.load()
    site_settings.time_zone = "America/New_York"
    site_settings.save()
    position = make_position()
    Position.objects.filter(pk=position.pk).update(
        starts_at=datetime(2030, 11, 8, 14, 0, tzinfo=UTC),  # 9:00 AM in New York
        ends_at=datetime(2030, 11, 8, 17, 0, tzinfo=UTC),
    )
    registration = services.register(volunteer, Position.objects.get(pk=position.pk))
    OutgoingEmail.objects.all().delete()

    with timezone.override(UTC):  # what a Celery worker has active
        messages.reminder(registration)

    email = OutgoingEmail.objects.get()
    assert "9:00 AM – 12:00 PM" in email.text_body
    assert "9:00 AM – 12:00 PM" in email.subject


# Temporary provider errors (rate limits, auth) are retried, not dropped.


@pytest.mark.parametrize("status_code", [401, 403, 408, 429])
def test_temporary_provider_errors_are_retried(volunteer, monkeypatch, status_code):
    def throttled(self, *args, **kwargs):
        raise AnymailAPIError("try later", status_code=status_code)

    monkeypatch.setattr(EmailMultiAlternatives, "send", throttled)
    email = outbox.queue(
        kind="registered", user=volunteer, subject="s", text_body="t", html_body="h"
    )
    with pytest.raises(Retry):
        send_outgoing.apply(args=(email.pk,), throw=True)
    email.refresh_from_db()
    assert email.status == "queued"


def test_bad_request_is_permanent(volunteer, monkeypatch):
    def bad(self, *args, **kwargs):
        raise AnymailAPIError("invalid", status_code=422)

    monkeypatch.setattr(EmailMultiAlternatives, "send", bad)
    email = outbox.queue(
        kind="registered", user=volunteer, subject="s", text_body="t", html_body="h"
    )
    send_outgoing(email.pk)
    email.refresh_from_db()
    assert email.status == "failed"


# Each email is sent by exactly one worker.


def test_row_being_sent_elsewhere_is_skipped(volunteer, mailoutbox):
    email = outbox.queue(
        kind="registered", user=volunteer, subject="s", text_body="t", html_body="h"
    )
    OutgoingEmail.objects.filter(pk=email.pk).update(status="sending")
    send_outgoing(email.pk)
    assert mailoutbox == []


def test_network_error_returns_row_to_queue(volunteer, monkeypatch):
    def down(self, *args, **kwargs):
        raise ConnectionResetError

    monkeypatch.setattr(EmailMultiAlternatives, "send", down)
    email = outbox.queue(
        kind="registered", user=volunteer, subject="s", text_body="t", html_body="h"
    )
    with pytest.raises(Retry):
        send_outgoing.apply(args=(email.pk,), throw=True)
    email.refresh_from_db()
    assert email.status == "queued"


def test_resend_stuck_recovers_abandoned_sends(volunteer, mailoutbox):
    email = outbox.queue(
        kind="registered", user=volunteer, subject="s", text_body="t", html_body="h"
    )
    OutgoingEmail.objects.filter(pk=email.pk).update(
        status="sending",
        created_at=timezone.now() - timedelta(minutes=30),
        updated_at=timezone.now() - timedelta(minutes=30),
    )
    resend_stuck()
    email.refresh_from_db()
    assert email.status == "sent"


# Bounce flags follow the right message.


def sent_email(user, message_id, to=None, sent_at=None):
    return OutgoingEmail.objects.create(
        to=to or user.email,
        user=user,
        kind="registered",
        subject="s",
        text_body="t",
        html_body="h",
        status="sent",
        provider_message_id=message_id,
        sent_at=sent_at or timezone.now(),
    )


def fire(event_type, message_id):
    tracking.send(
        sender=object,
        event=AnymailTrackingEvent(event_type=event_type, message_id=message_id, description="x"),
        esp_name="Test",
    )


def test_older_delivery_does_not_clear_newer_bounce(volunteer):
    sent_email(volunteer, "older", sent_at=timezone.now() - timedelta(minutes=10))
    sent_email(volunteer, "newer", sent_at=timezone.now() - timedelta(minutes=5))
    fire("bounced", "newer")
    fire("delivered", "older")
    volunteer.profile.refresh_from_db()
    assert volunteer.profile.email_undeliverable_at is not None


def test_bounce_from_old_address_does_not_flag_new_one(volunteer):
    sent_email(volunteer, "old", to="previous@example.org")
    fire("bounced", "old")
    volunteer.profile.refresh_from_db()
    assert volunteer.profile.email_undeliverable_at is None


# Calendar sequence numbers only go up across event cancel and reinstate.


def test_calendar_sequence_increases_across_cancel_and_reinstate(
    client, coordinator, volunteer, make_position
):
    position = make_position()
    services.register(volunteer, position)
    client.force_login(coordinator)
    client.post(reverse("manage_event_action", args=[position.event_id, "cancel"]))
    client.post(reverse("manage_event_action", args=[position.event_id, "reinstate"]))

    sequences = [
        int(re.search(r"SEQUENCE:(\d+)", email.ics).group(1))
        for email in OutgoingEmail.objects.filter(user=volunteer).exclude(ics="").order_by("pk")
    ]
    assert sequences == sorted(sequences)
    assert len(set(sequences)) == len(sequences)  # strictly increasing
    assert len(sequences) == 3  # registered, event_cancelled, event_reinstated


# Tracking webhooks must be authenticated in production.


def test_webhook_secret_required_for_anymail_in_production():
    from core.env import check_anymail_webhook_secret

    with pytest.raises(ImproperlyConfigured, match="ANYMAIL_WEBHOOK_SECRET"):
        check_anymail_webhook_secret(
            "anymail.backends.postmark.EmailBackend", debug=False, anymail={}
        )
    check_anymail_webhook_secret(
        "anymail.backends.postmark.EmailBackend", debug=False, anymail={"WEBHOOK_SECRET": "u:p"}
    )
    check_anymail_webhook_secret("anymail.backends.postmark.EmailBackend", debug=True, anymail={})
    check_anymail_webhook_secret(
        "django.core.mail.backends.smtp.EmailBackend", debug=False, anymail={}
    )
