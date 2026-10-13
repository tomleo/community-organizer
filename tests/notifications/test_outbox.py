import smtplib
from datetime import timedelta

import pytest
from django.db import transaction
from django.utils import timezone

from notifications import outbox
from notifications.models import OutgoingEmail
from notifications.tasks import resend_stuck, send_outgoing

pytestmark = pytest.mark.django_db


def queue_for(user, **overrides):
    values = dict(
        kind="registered", user=user, subject="Hi", text_body="Text", html_body="<p>Html</p>"
    )
    values.update(overrides)
    return outbox.queue(**values)


def test_queue_sends_after_commit(volunteer, mailoutbox, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        email = queue_for(volunteer)
    email.refresh_from_db()
    assert email.status == "sent"
    assert email.sent_at is not None
    assert mailoutbox[0].to == [volunteer.email]
    assert mailoutbox[0].alternatives[0][0] == "<p>Html</p>"


def test_rolled_back_transaction_sends_nothing(
    volunteer, mailoutbox, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        try:
            with transaction.atomic():
                queue_for(volunteer)
                raise RuntimeError("refused")
        except RuntimeError:
            pass
    assert OutgoingEmail.objects.count() == 0
    assert mailoutbox == []


def test_dedupe_key(volunteer):
    assert queue_for(volunteer, dedupe_key="reminder:1") is not None
    assert queue_for(volunteer, dedupe_key="reminder:1") is None
    assert OutgoingEmail.objects.count() == 1


def test_flagged_address_is_suppressed(volunteer, mailoutbox, django_capture_on_commit_callbacks):
    volunteer.profile.email_undeliverable_at = timezone.now()
    volunteer.profile.save()
    with django_capture_on_commit_callbacks(execute=True):
        email = queue_for(volunteer)
    assert email.status == "suppressed"
    assert mailoutbox == []


def test_ics_attached_with_method(volunteer, mailoutbox, django_capture_on_commit_callbacks):
    ics = "BEGIN:VCALENDAR\r\nMETHOD:CANCEL\r\nEND:VCALENDAR\r\n"
    with django_capture_on_commit_callbacks(execute=True):
        queue_for(volunteer, ics=ics)
    filename, content, mimetype = mailoutbox[0].attachments[0]
    assert filename == "shift.ics"
    assert mimetype == "text/calendar; method=CANCEL"


def test_reply_to_contact_email(volunteer, mailoutbox, django_capture_on_commit_callbacks):
    from organization.models import SiteSettings

    site_settings = SiteSettings.load()
    site_settings.contact_email = "help@org.example"
    site_settings.save()
    with django_capture_on_commit_callbacks(execute=True):
        queue_for(volunteer)
    assert mailoutbox[0].reply_to == ["help@org.example"]


def test_message_id_recorded(volunteer, monkeypatch):
    from django.core.mail import EmailMultiAlternatives

    def fake_send(self, *args, **kwargs):
        self.anymail_status = type("Status", (), {"message_id": "abc-123"})()
        return 1

    monkeypatch.setattr(EmailMultiAlternatives, "send", fake_send)
    email = queue_for(volunteer)
    send_outgoing(email.pk)
    email.refresh_from_db()
    assert email.provider_message_id == "abc-123"


def test_permanent_error_marks_failed(volunteer, monkeypatch):
    from django.core.mail import EmailMultiAlternatives

    def refuse(self, *args, **kwargs):
        raise smtplib.SMTPRecipientsRefused({volunteer.email: (550, b"no such user")})

    monkeypatch.setattr(EmailMultiAlternatives, "send", refuse)
    email = queue_for(volunteer)
    send_outgoing(email.pk)
    email.refresh_from_db()
    assert email.status == "failed"
    assert "550" in email.error


def test_send_skips_rows_not_queued(volunteer, mailoutbox):
    email = queue_for(volunteer)
    OutgoingEmail.objects.filter(pk=email.pk).update(status="sent")
    send_outgoing(email.pk)
    assert mailoutbox == []


def test_resend_stuck(volunteer, mailoutbox):
    stuck = queue_for(volunteer)
    old = queue_for(volunteer)
    fresh = queue_for(volunteer)
    half_hour_ago = timezone.now() - timedelta(minutes=30)
    two_days_ago = timezone.now() - timedelta(days=2)
    OutgoingEmail.objects.filter(pk=stuck.pk).update(
        created_at=half_hour_ago, updated_at=half_hour_ago
    )
    OutgoingEmail.objects.filter(pk=old.pk).update(created_at=two_days_ago, updated_at=two_days_ago)

    resend_stuck()

    statuses = dict(OutgoingEmail.objects.values_list("pk", "status"))
    assert statuses[stuck.pk] == "sent"
    assert statuses[old.pk] == "failed"
    assert statuses[fresh.pk] == "queued"


def test_beat_schedule():
    from django.conf import settings

    assert settings.CELERY_BEAT_SCHEDULE["resend-stuck-emails"] == {
        "task": "notifications.tasks.resend_stuck",
        "schedule": 600,
    }
