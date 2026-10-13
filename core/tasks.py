import logging
import smtplib

from celery import shared_task
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.db import transaction

from core.images import RESIZE_SIZES, create_variants

logger = logging.getLogger(__name__)


# Permanent rejections fail at once; retrying them only delays the error.
PERMANENT_SMTP_ERRORS = (
    smtplib.SMTPAuthenticationError,
    smtplib.SMTPRecipientsRefused,
    smtplib.SMTPSenderRefused,
)


# smtplib.SMTPException and socket errors are OSError subclasses. Backoff of 30s doubling to a
# 10 minute cap rides out a provider outage of roughly a quarter of an hour.
@shared_task(
    autoretry_for=(OSError,),
    dont_autoretry_for=PERMANENT_SMTP_ERRORS,
    retry_backoff=30,
    retry_backoff_max=600,
    max_retries=6,
)
def send_email(subject, body, from_email, to, html_body=None, headers=None, reply_to=None):
    message = EmailMultiAlternatives(
        subject, body, from_email, to, headers=headers, reply_to=reply_to
    )
    if html_body:
        message.attach_alternative(html_body, "text/html")
    message.send()


@shared_task
def resize_image(name, sizes=None):
    try:
        create_variants(name, tuple(sizes) if sizes else RESIZE_SIZES)
    except Exception:
        logger.exception("Could not resize image %s; keeping the original.", name)


def queue_email(message: EmailMessage) -> None:
    html_body = next(
        (
            content
            for content, mimetype in getattr(message, "alternatives", [])
            if mimetype == "text/html"
        ),
        None,
    )
    send_email.delay(
        message.subject,
        message.body,
        message.from_email,
        list(message.to),
        html_body=html_body,
        headers=dict(message.extra_headers) or None,
        reply_to=list(message.reply_to) or None,
    )


def queue_resize(field_file, sizes=None) -> None:
    if not field_file:
        return
    name = field_file.name
    size_list = list(sizes) if sizes else None
    transaction.on_commit(lambda: resize_image.delay(name, size_list))
