"""Who a group message goes to, and creating the message."""

from collections import Counter
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.text import Truncator

from events.models import Event, Position
from notifications.models import Message

ROSTER_STATUSES = ("registered", "offered", "waitlisted")
STATUS_LABELS = {"registered": "registered", "offered": "offered", "waitlisted": "waitlisted"}


@dataclass
class Audience:
    description: str
    users: list = field(default_factory=list)
    skipped: dict = field(default_factory=dict)

    @property
    def skipped_total(self) -> int:
        return sum(self.skipped.values())


def _split(users, *, respect_opt_out):
    recipients, skipped = [], Counter()
    for user in users:
        profile = user.profile
        if not user.is_active or profile.deleted_at:
            skipped["deleted"] += 1
        elif profile.email_undeliverable_at:
            skipped["undeliverable"] += 1
        elif respect_opt_out and not profile.announcement_emails:
            skipped["opted out"] += 1
        else:
            recipients.append(user)
    return recipients, dict(skipped)


def _users():
    return get_user_model().objects.select_related("profile").order_by("pk")


def audience_for_volunteers(ids) -> Audience:
    users, skipped = _split(_users().filter(pk__in=ids), respect_opt_out=True)
    return Audience("Selected volunteers", users, skipped)


def _statuses(statuses):
    chosen = [status for status in statuses if status in ROSTER_STATUSES]
    return chosen or ["registered"]


def audience_for_position(position, statuses) -> Audience:
    statuses = _statuses(statuses)
    users = (
        _users()
        .filter(registrations__position=position, registrations__status__in=statuses)
        .distinct()
    )
    recipients, skipped = _split(users, respect_opt_out=False)
    description = f"{position.title} · {position.event.title} ({', '.join(statuses)})"
    return Audience(description, recipients, skipped)


def audience_for_event(event, statuses) -> Audience:
    statuses = _statuses(statuses)
    users = (
        _users()
        .filter(registrations__position__event=event, registrations__status__in=statuses)
        .distinct()
    )
    recipients, skipped = _split(users, respect_opt_out=False)
    return Audience(f"{event.title} ({', '.join(statuses)})", recipients, skipped)


def audience_from_params(params) -> Audience | None:
    """Build the audience from ?ids=…, ?position=… or ?event=… (plus repeated ?statuses=…)."""
    statuses = params.getlist("statuses")
    if params.get("position", "").isdigit():
        position = Position.objects.select_related("event").filter(pk=params["position"]).first()
        return audience_for_position(position, statuses) if position else None
    if params.get("event", "").isdigit():
        event = Event.objects.filter(pk=params["event"]).first()
        return audience_for_event(event, statuses) if event else None
    ids = [value for value in params.getlist("ids") if value.isdigit()]
    return audience_for_volunteers(ids) if ids else None


def create_message(sender, subject, body, audience, send_token=None) -> Message:
    from notifications.tasks import send_message

    message = Message.objects.create(
        sender=sender,
        subject=subject,
        body=body,
        # Titles can be long; the column holds 255 characters.
        audience=Truncator(audience.description).chars(
            Message._meta.get_field("audience").max_length
        ),
        send_token=send_token,
        recipient_count=len(audience.users),
        skipped_count=audience.skipped_total,
    )
    user_ids = [user.pk for user in audience.users]
    transaction.on_commit(lambda: send_message.delay(message.pk, user_ids))
    return message
