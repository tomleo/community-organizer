from datetime import timedelta

from django.db.models import Q

from events.models import Position
from registrations.models import Registration
from registrations.selectors import with_capacity

ACTIVITY_WINDOW = timedelta(hours=24)
SOON_WINDOW = timedelta(hours=48)


def build_digest(now) -> dict:
    since = now - ACTIVITY_WINDOW
    recent = (
        Registration.objects.filter(position__starts_at__gt=now)
        .filter(Q(created_at__gte=since) | Q(ended_at__gte=since))
        .select_related("volunteer__profile", "position__event")
        .order_by("position__starts_at", "pk")
    )
    activity = [
        {
            "position": registration.position,
            "volunteer": registration.volunteer.profile.full_name or registration.volunteer.email,
            "change": registration.get_status_display().lower(),
        }
        for registration in recent
    ]
    soon = with_capacity(
        Position.objects.filter(
            starts_at__gt=now,
            starts_at__lte=now + SOON_WINDOW,
            event__status="published",
            event__archived_at__isnull=True,
        ).select_related("event")
    ).order_by("starts_at")
    underfilled = []
    for position in soon:
        open_spots = position.slots - (position.held_parties + position.held_guests)
        if open_spots > 0:
            underfilled.append({"position": position, "open": open_spots})
    return {"activity": activity, "underfilled": underfilled}
