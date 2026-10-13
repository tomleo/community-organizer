import logging

import pytest
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.mail import EmailMultiAlternatives

from core.images import variant_name
from core.tasks import queue_email, queue_resize, resize_image, send_email


def test_send_email_delivers_text_and_html(mailoutbox):
    send_email.delay(
        "Subject", "Text body", "from@example.org", ["to@example.org"], html_body="<p>Hi</p>"
    )

    assert len(mailoutbox) == 1
    message = mailoutbox[0]
    assert message.subject == "Subject"
    assert message.body == "Text body"
    assert message.alternatives[0][0] == "<p>Hi</p>"


def test_queue_email_preserves_message(mailoutbox):
    message = EmailMultiAlternatives(
        "Hello",
        "Plain",
        "from@example.org",
        ["a@example.org"],
        headers={"X-Campaign": "welcome"},
        reply_to=["contact@example.org"],
    )
    message.attach_alternative("<b>Rich</b>", "text/html")

    queue_email(message)

    sent = mailoutbox[0]
    assert sent.to == ["a@example.org"]
    assert sent.reply_to == ["contact@example.org"]
    assert sent.extra_headers["X-Campaign"] == "welcome"
    assert sent.alternatives[0][0] == "<b>Rich</b>"


def test_resize_image_logs_and_swallows_failures(caplog):
    with caplog.at_level(logging.ERROR, logger="core.tasks"):
        resize_image.delay("missing/file.png")
    assert "missing/file.png" in caplog.text


@pytest.mark.django_db
def test_queue_resize_runs_after_commit(make_image_file, django_capture_on_commit_callbacks):
    name = default_storage.save("uploads/photo.png", make_image_file())

    class FakeFieldFile:
        def __init__(self, name):
            self.name = name

        def __bool__(self):
            return True

    with django_capture_on_commit_callbacks(execute=True):
        queue_resize(FakeFieldFile(name))

    assert default_storage.exists(variant_name(name, 128))


def test_queue_resize_ignores_empty_file():
    queue_resize(None)


def test_cache_and_broker_use_different_valkey_databases():
    assert settings.CACHES["default"]["LOCATION"] != settings.CELERY_BROKER_URL


def test_send_email_retries_span_minutes():
    assert send_email.max_retries >= 5
    assert send_email.retry_backoff >= 30
    assert send_email.retry_backoff_max >= 600


def _failing_send(exc):
    def send(self, *args, **kwargs):
        raise exc

    return send


def test_send_email_retries_transient_errors(monkeypatch):
    from celery.exceptions import Retry

    monkeypatch.setattr(EmailMultiAlternatives, "send", _failing_send(ConnectionResetError()))
    with pytest.raises(Retry):
        send_email.apply(args=("s", "b", "f@example.org", ["t@example.org"]), throw=True)


def test_send_email_does_not_retry_permanent_rejections(monkeypatch):
    import smtplib

    refused = smtplib.SMTPRecipientsRefused({"t@example.org": (550, b"no such user")})
    monkeypatch.setattr(EmailMultiAlternatives, "send", _failing_send(refused))
    with pytest.raises(smtplib.SMTPRecipientsRefused):
        send_email.apply(args=("s", "b", "f@example.org", ["t@example.org"]), throw=True)


@pytest.mark.django_db
def test_queue_resize_with_custom_sizes(make_image_file, django_capture_on_commit_callbacks):
    name = default_storage.save("uploads/wide.png", make_image_file(size=(2000, 1000)))

    class Stored:
        def __init__(self, name):
            self.name = name

        def __bool__(self):
            return True

    with django_capture_on_commit_callbacks(execute=True):
        queue_resize(Stored(name), sizes=(1600, 800))

    assert default_storage.exists(variant_name(name, 1600))
    assert default_storage.exists(variant_name(name, 800))
    assert not default_storage.exists(variant_name(name, 128))
