import logging
import re
from datetime import timedelta
from zoneinfo import ZoneInfo

from anymail.exceptions import AnymailAPIError, AnymailRecipientsRefused
from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from core.tasks import PERMANENT_SMTP_ERRORS
from notifications import messages
from notifications.digest import build_digest
from notifications.models import Message, OutgoingEmail
from organization.models import SiteSettings
from registrations.models import Registration

logger = logging.getLogger(__name__)

STUCK_AFTER = timedelta(minutes=10)
GIVE_UP_AFTER = timedelta(hours=24)
_METHOD = re.compile(r"^METHOD:(\w+)", re.MULTILINE)


def _build_message(email) -> EmailMultiAlternatives:
    contact = SiteSettings.load().contact_email
    reply_to = email.reply_to or contact
    message = EmailMultiAlternatives(
        email.subject,
        email.text_body,
        None,  # DEFAULT_FROM_EMAIL
        [email.to],
        reply_to=[reply_to] if reply_to else None,
    )
    message.attach_alternative(email.html_body, "text/html")
    if email.ics:
        match = _METHOD.search(email.ics)
        method = match.group(1) if match else "PUBLISH"
        message.attach("shift.ics", email.ics, f"text/calendar; method={method}")
    return message


# Provider errors worth retrying: auth problems (a rotated key gets fixed), timeouts, rate limits.
TEMPORARY_HTTP_STATUSES = {401, 403, 408, 429}


def _describe(error) -> str:
    try:
        return str(error)[:2000]
    except Exception:  # some exception types can't format themselves without a response
        return error.__class__.__name__


def _fail(email, error):
    email.status = OutgoingEmail.Status.FAILED
    email.error = _describe(error)
    email.save(update_fields=["status", "error", "updated_at"])


def _requeue(email):
    email.status = OutgoingEmail.Status.QUEUED
    email.save(update_fields=["status", "updated_at"])


@shared_task(
    autoretry_for=(OSError, AnymailAPIError), retry_backoff=30, retry_backoff_max=600, max_retries=6
)
def send_outgoing(pk):
    # Claim the row so only one worker sends it, even when retries and resend_stuck overlap.
    claimed = OutgoingEmail.objects.filter(pk=pk, status=OutgoingEmail.Status.QUEUED).update(
        status=OutgoingEmail.Status.SENDING, updated_at=timezone.now()
    )
    if not claimed:
        return
    email = OutgoingEmail.objects.get(pk=pk)
    message = _build_message(email)
    try:
        message.send()
    except (AnymailRecipientsRefused, *PERMANENT_SMTP_ERRORS) as exc:
        _fail(email, exc)
        return
    except AnymailAPIError as exc:
        status_code = exc.status_code or 0
        if 400 <= status_code < 500 and status_code not in TEMPORARY_HTTP_STATUSES:
            _fail(email, exc)
            return
        _requeue(email)
        raise
    except OSError:
        _requeue(email)
        raise
    status = getattr(message, "anymail_status", None)
    email.provider_message_id = (getattr(status, "message_id", None) or "") if status else ""
    if not isinstance(email.provider_message_id, str):  # several recipients: a set of ids
        email.provider_message_id = ""
    email.status = OutgoingEmail.Status.SENT
    email.sent_at = timezone.now()
    email.save(update_fields=["status", "sent_at", "provider_message_id", "updated_at"])


@shared_task
def resend_stuck():
    now = timezone.now()
    # A worker that died mid-send leaves the row "sending"; put it back in the queue.
    OutgoingEmail.objects.filter(
        status=OutgoingEmail.Status.SENDING, updated_at__lt=now - STUCK_AFTER
    ).update(status=OutgoingEmail.Status.QUEUED, updated_at=now - STUCK_AFTER)
    stuck = OutgoingEmail.objects.filter(
        status=OutgoingEmail.Status.QUEUED, updated_at__lte=now - STUCK_AFTER
    )
    stuck.filter(created_at__lt=now - GIVE_UP_AFTER).update(
        status=OutgoingEmail.Status.FAILED, error="Gave up after 24 hours.", updated_at=now
    )
    for pk in stuck.values_list("pk", flat=True):
        send_outgoing.delay(pk)


DIGEST_HOUR = 7


@shared_task
def send_reminders(now=None):
    now = now or timezone.now()
    hours = SiteSettings.load().reminder_hours_before
    if not hours:
        return 0
    window = timedelta(hours=hours)
    due = Registration.objects.filter(
        status=Registration.Status.REGISTERED,
        position__starts_at__gt=now,
        position__starts_at__lte=now + window,
        position__event__status="published",
        position__event__archived_at__isnull=True,
        volunteer__profile__reminder_emails=True,
        # Registered before the reminder window opened; later sign-ups have their confirmation.
        created_at__lt=F("position__starts_at") - window,
    ).select_related("volunteer__profile", "position__event__location", "position__location")
    sent = 0
    for registration in due:
        with transaction.atomic():
            if messages.reminder(registration) is not None:
                sent += 1
    return sent


@shared_task
def send_staff_digests(now=None):
    now = now or timezone.now()
    site_settings = SiteSettings.load()
    local = now.astimezone(ZoneInfo(site_settings.time_zone))
    if local.hour != DIGEST_HOUR:
        return 0
    staff = [
        user
        for user in get_user_model()
        .objects.filter(is_active=True, profile__staff_digest=True)
        .select_related("profile")
        if user.has_perm("registrations.view_registration")
    ]
    if not staff:
        return 0
    digest = build_digest(now)
    if not digest["activity"] and not digest["underfilled"]:
        return 0
    sent = 0
    for user in staff:
        with transaction.atomic():
            if messages.staff_digest(user, digest, local.date().isoformat()) is not None:
                sent += 1
    return sent


@shared_task
def send_message(message_id, user_ids):
    message = Message.objects.select_related("sender__profile").get(pk=message_id)
    for user in get_user_model().objects.filter(pk__in=user_ids).select_related("profile"):
        with transaction.atomic():
            messages.group_message(message, user)
