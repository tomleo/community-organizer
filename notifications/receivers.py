"""Delivery tracking from anymail, and clearing the undeliverable flag."""

import logging

from allauth.account.signals import email_changed
from anymail.signals import tracking
from django.dispatch import receiver
from django.utils import timezone

from notifications.models import OutgoingEmail

logger = logging.getLogger(__name__)

STATUS_FOR_EVENT = {
    "delivered": OutgoingEmail.Status.DELIVERED,
    "bounced": OutgoingEmail.Status.BOUNCED,  # hard bounce; soft bounces are "deferred"
    "complained": OutgoingEmail.Status.COMPLAINED,
}


@receiver(tracking)
def handle_tracking(sender, event, esp_name, **kwargs):
    status = STATUS_FOR_EVENT.get(event.event_type)
    if status is None or not event.message_id:
        return
    email = (
        OutgoingEmail.objects.select_related("user__profile")
        .filter(provider_message_id=event.message_id)
        .first()
    )
    if email is None:
        logger.info("Tracking event for unknown message %s from %s", event.message_id, esp_name)
        return
    if not email.can_move_to(status):
        return
    email.status = status
    if status != OutgoingEmail.Status.DELIVERED:
        email.error = event.description or event.mta_response or ""
    email.save(update_fields=["status", "error", "updated_at"])

    profile = getattr(email.user, "profile", None) if email.user else None
    if profile is None or email.to.lower() != email.user.email.lower():
        return  # sent to an address the volunteer no longer uses
    if status == OutgoingEmail.Status.DELIVERED:
        flagged_at = profile.email_undeliverable_at
        # Only a message sent after the problem was flagged proves the address works again.
        if flagged_at and email.sent_at and email.sent_at > flagged_at:
            profile.email_undeliverable_at = None
            profile.email_undeliverable_reason = ""
            profile.save(
                update_fields=["email_undeliverable_at", "email_undeliverable_reason", "updated_at"]
            )
        return
    reason = (
        "Marked our email as spam"
        if status == OutgoingEmail.Status.COMPLAINED
        else f"Bounced: {event.description or event.mta_response or 'address rejected'}"
    )
    profile.email_undeliverable_at = timezone.now()
    profile.email_undeliverable_reason = reason[:255]
    profile.save(
        update_fields=["email_undeliverable_at", "email_undeliverable_reason", "updated_at"]
    )


@receiver(email_changed)
def clear_flag_on_email_change(sender, request, user, **kwargs):
    profile = getattr(user, "profile", None)
    if profile and profile.email_undeliverable_at:
        profile.email_undeliverable_at = None
        profile.email_undeliverable_reason = ""
        profile.save(
            update_fields=["email_undeliverable_at", "email_undeliverable_reason", "updated_at"]
        )
