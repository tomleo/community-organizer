from django.conf import settings
from django.db import models


class OutgoingEmail(models.Model):
    """Outbox and delivery log: one row per email we send (or decide not to send)."""

    class Kind(models.TextChoices):
        REGISTERED = "registered", "Registration confirmed"
        WAITLISTED = "waitlisted", "Joined waitlist"
        OFFERED = "offered", "Spot offered"
        AUTO_REGISTERED = "auto_registered", "Registered from waitlist"
        OFFER_EXPIRED = "offer_expired", "Offer expired"
        CANCELLED = "cancelled", "Registration cancelled"
        REMOVED = "removed", "Removed by staff"
        EVENT_CANCELLED = "event_cancelled", "Event cancelled"
        EVENT_REINSTATED = "event_reinstated", "Event reinstated"
        POSITION_CHANGED = "position_changed", "Shift changed"
        REMINDER = "reminder", "Shift reminder"
        STAFF_DIGEST = "staff_digest", "Staff digest"
        MESSAGE = "message", "Message from organizers"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        BOUNCED = "bounced", "Bounced"
        COMPLAINED = "complained", "Marked as spam"
        FAILED = "failed", "Failed"
        SUPPRESSED = "suppressed", "Not sent (address undeliverable)"

    to = models.EmailField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outgoing_emails",
    )
    kind = models.CharField(max_length=30, choices=Kind.choices)
    dedupe_key = models.CharField(max_length=200, null=True, blank=True, unique=True)
    subject = models.CharField(max_length=255)
    text_body = models.TextField()
    html_body = models.TextField()
    ics = models.TextField(blank=True)
    reply_to = models.EmailField(blank=True)
    message = models.ForeignKey(
        "Message", on_delete=models.SET_NULL, null=True, blank=True, related_name="emails"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    provider_message_id = models.CharField(max_length=255, blank=True, db_index=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} to {self.to}"

    def can_move_to(self, status) -> bool:
        return STATUS_RANK[status] > STATUS_RANK[self.status]


STATUS_RANK = {
    OutgoingEmail.Status.QUEUED: 0,
    OutgoingEmail.Status.SENDING: 1,
    OutgoingEmail.Status.SENT: 2,
    OutgoingEmail.Status.DELIVERED: 3,
    OutgoingEmail.Status.BOUNCED: 4,
    OutgoingEmail.Status.COMPLAINED: 4,
    OutgoingEmail.Status.FAILED: 5,
    OutgoingEmail.Status.SUPPRESSED: 5,
}


class Message(models.Model):
    """A group email from staff; each recipient's copy is an OutgoingEmail."""

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    subject = models.CharField(max_length=200)
    body = models.TextField()
    audience = models.CharField(max_length=255)
    recipient_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    # Set from the preview form so a double-clicked or re-submitted Send creates one message.
    send_token = models.UUIDField(null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.subject
