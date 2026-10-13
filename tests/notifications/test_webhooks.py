import pytest
from anymail.signals import AnymailTrackingEvent, tracking
from django.urls import reverse
from django.utils import timezone

from notifications.models import OutgoingEmail

pytestmark = pytest.mark.django_db


def sent_email(user, message_id="msg-1"):
    return OutgoingEmail.objects.create(
        to=user.email,
        user=user,
        kind="registered",
        subject="s",
        text_body="t",
        html_body="h",
        status="sent",
        provider_message_id=message_id,
        sent_at=timezone.now(),
    )


def fire(event_type, message_id="msg-1", description="Mailbox does not exist"):
    event = AnymailTrackingEvent(
        event_type=event_type, message_id=message_id, description=description
    )
    tracking.send(sender=object, event=event, esp_name="Test")


def test_delivered(volunteer):
    email = sent_email(volunteer)
    fire("delivered")
    email.refresh_from_db()
    assert email.status == "delivered"


def test_bounce_flags_address(volunteer):
    email = sent_email(volunteer)
    fire("bounced")
    email.refresh_from_db()
    volunteer.profile.refresh_from_db()
    assert email.status == "bounced"
    assert volunteer.profile.email_undeliverable_at is not None
    assert "Mailbox does not exist" in volunteer.profile.email_undeliverable_reason


def test_complaint_flags_address(volunteer):
    sent_email(volunteer)
    fire("delivered")
    fire("complained", description="")
    volunteer.profile.refresh_from_db()
    assert volunteer.profile.email_undeliverable_reason == "Marked our email as spam"


def test_deferred_does_not_flag(volunteer):
    email = sent_email(volunteer)
    fire("deferred")
    email.refresh_from_db()
    volunteer.profile.refresh_from_db()
    assert email.status == "sent"
    assert volunteer.profile.email_undeliverable_at is None


def test_late_delivered_does_not_undo_bounce(volunteer):
    email = sent_email(volunteer)
    fire("bounced")
    fire("delivered")
    email.refresh_from_db()
    volunteer.profile.refresh_from_db()
    assert email.status == "bounced"
    assert volunteer.profile.email_undeliverable_at is not None


def test_later_delivery_clears_flag(volunteer):
    sent_email(volunteer, "msg-1")
    fire("bounced", "msg-1")
    sent_email(volunteer, "msg-2")
    fire("delivered", "msg-2")
    volunteer.profile.refresh_from_db()
    assert volunteer.profile.email_undeliverable_at is None


def test_unknown_message_ignored(volunteer):
    fire("bounced", "nope")
    volunteer.profile.refresh_from_db()
    assert volunteer.profile.email_undeliverable_at is None


def test_email_change_clears_flag(volunteer):
    from allauth.account.signals import email_changed

    volunteer.profile.email_undeliverable_at = timezone.now()
    volunteer.profile.save()
    email_changed.send(
        sender=type(volunteer),
        request=None,
        user=volunteer,
        from_email_address=None,
        to_email_address=None,
    )
    volunteer.profile.refresh_from_db()
    assert volunteer.profile.email_undeliverable_at is None


def test_banner_and_roster_warning(client, volunteer, coordinator, make_position):
    from registrations import services

    volunteer.profile.email_undeliverable_at = timezone.now()
    volunteer.profile.email_undeliverable_reason = "Bounced"
    volunteer.profile.save()
    position = make_position()
    services.register(volunteer, position)

    client.force_login(volunteer)
    content = client.get(reverse("home")).content.decode()
    assert (
        "We couldn&#x27;t deliver email to you" in content
        or "We couldn't deliver email to you" in content
    )
    assert reverse("account_email") in content

    client.force_login(coordinator)
    roster = client.get(reverse("manage_roster", args=[position.pk])).content.decode()
    assert "⚠" in roster
    assert 'title="Bounced"' in roster


def test_webhook_requires_secret(client, settings):
    settings.ANYMAIL = {"WEBHOOK_SECRET": "user:pass"}
    response = client.post(
        "/anymail/postmark/tracking/", data="{}", content_type="application/json"
    )
    assert response.status_code in (400, 403)
