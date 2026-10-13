from datetime import UTC
from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone
from icalendar import Calendar, Event

from core.richtext import plain_text
from notifications.render import absolute_url


def shift_ics(registration, *, method="PUBLISH", sequence_bump=None) -> str:
    """`sequence_bump` defaults to 1 for CANCEL (a registration's last word) and 0 otherwise."""
    position = registration.position
    event = position.event
    place = position.effective_location
    cancel = method == "CANCEL"

    calendar = Calendar()
    calendar.add("prodid", "-//Community Organizer//EN")
    calendar.add("version", "2.0")
    calendar.add("method", method)

    entry = Event()
    entry.add("uid", f"registration-{registration.pk}@{urlsplit(settings.SITE_URL).hostname}")
    if sequence_bump is None:
        sequence_bump = 1 if cancel else 0
    entry.add("sequence", position.schedule_version + sequence_bump)
    entry.add("dtstamp", timezone.now().astimezone(UTC))
    entry.add("dtstart", position.starts_at.astimezone(UTC))
    entry.add("dtend", position.ends_at.astimezone(UTC))
    entry.add("summary", f"{position.title} · {event.title}")
    entry.add(
        "location",
        f"{place.name}, {place.address_line1}, {place.city}, {place.region} {place.postal_code}",
    )
    description = plain_text(position.description)
    link = absolute_url(event.get_absolute_url())
    entry.add("description", f"{description}\n\n{link}".strip())
    entry.add("status", "CANCELLED" if cancel else "CONFIRMED")
    calendar.add_component(entry)
    return calendar.to_ical().decode()
