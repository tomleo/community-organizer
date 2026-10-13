import pytest
from django.urls import reverse
from django.utils import timezone

from notifications.models import OutgoingEmail
from registrations import services

pytestmark = pytest.mark.django_db


def form_data(position, **changes):
    fmt = "%Y-%m-%dT%H:%M"
    data = {
        "title": position.title,
        "starts_at": timezone.localtime(position.starts_at).strftime(fmt),
        "ends_at": timezone.localtime(position.ends_at).strftime(fmt),
        "slots": str(position.slots),
        "location": position.location_id or "",
        "description": position.description,
    }
    data.update(changes)
    return data


def test_event_cancel_and_reinstate(client, coordinator, make_volunteer, make_position):
    position = make_position(slots=1)
    services.register(make_volunteer(1), position)
    services.register(make_volunteer(2), position)
    client.force_login(coordinator)
    OutgoingEmail.objects.all().delete()

    client.post(reverse("manage_event_action", args=[position.event_id, "cancel"]))
    client.post(reverse("manage_event_action", args=[position.event_id, "reinstate"]))

    rows = list(OutgoingEmail.objects.order_by("pk").values_list("kind", "ics"))
    assert [kind for kind, _ in rows] == ["event_cancelled"] * 2 + ["event_reinstated"] * 2
    cancel_ics = [ics for kind, ics in rows if kind == "event_cancelled"]
    assert sum("METHOD:CANCEL" in ics for ics in cancel_ics) == 1  # only the registered one


def test_time_change_emails_and_bumps_version(client, coordinator, volunteer, make_position):
    position = make_position()
    services.register(volunteer, position)
    client.force_login(coordinator)
    later = timezone.localtime(position.starts_at + timezone.timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M"
    )

    client.post(
        reverse("manage_position_edit", args=[position.pk]), form_data(position, starts_at=later)
    )

    position.refresh_from_db()
    assert position.schedule_version == 1
    email = OutgoingEmail.objects.get(kind="position_changed")
    assert "SEQUENCE:1" in email.ics
    assert "Community Center" in email.text_body  # old location named


def test_description_only_edit_sends_nothing(client, coordinator, volunteer, make_position):
    position = make_position()
    services.register(volunteer, position)
    client.force_login(coordinator)
    client.post(
        reverse("manage_position_edit", args=[position.pk]),
        form_data(position, description="<div>New notes</div>"),
    )
    position.refresh_from_db()
    assert position.schedule_version == 0
    assert not OutgoingEmail.objects.filter(kind="position_changed").exists()
