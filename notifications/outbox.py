"""Queue emails inside the triggering transaction; they are sent after it commits."""

from django.db import IntegrityError, transaction

from notifications.models import OutgoingEmail


def queue(
    *,
    kind,
    user,
    subject,
    text_body,
    html_body,
    ics="",
    to=None,
    dedupe_key=None,
    reply_to="",
    message=None,
) -> OutgoingEmail | None:
    """Create the outbox row. Returns None if `dedupe_key` was already used."""
    from notifications.tasks import send_outgoing

    if dedupe_key and OutgoingEmail.objects.filter(dedupe_key=dedupe_key).exists():
        return None
    profile = getattr(user, "profile", None) if user else None
    flagged = bool(profile and (profile.email_undeliverable_at or profile.deleted_at))
    email = OutgoingEmail(
        to=to or user.email,
        user=user,
        kind=kind,
        dedupe_key=dedupe_key,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        ics=ics,
        reply_to=reply_to,
        message=message,
        status=OutgoingEmail.Status.SUPPRESSED if flagged else OutgoingEmail.Status.QUEUED,
    )
    try:
        with transaction.atomic():
            email.save()
    except IntegrityError:
        return None  # same dedupe key queued concurrently
    if not flagged:
        transaction.on_commit(lambda: send_outgoing.delay(email.pk))
    return email
