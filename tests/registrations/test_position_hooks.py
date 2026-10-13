import pytest
from django.urls import reverse
from django.utils import timezone

from registrations import services

pytestmark = pytest.mark.django_db


def form_data(position, **changes):
    fmt = "%Y-%m-%dT%H:%M"
    data = {
        "title": position.title,
        "starts_at": timezone.localtime(position.starts_at).strftime(fmt),
        "ends_at": timezone.localtime(position.ends_at).strftime(fmt),
        "slots": str(position.slots),
        "location": "",
        "description": "",
    }
    data.update(changes)
    return data


def test_slots_cannot_drop_below_taken(client, coordinator, make_volunteer, make_position):
    position = make_position(slots=3)
    services.register(make_volunteer(1), position)
    services.register(make_volunteer(2), position)
    client.force_login(coordinator)
    response = client.post(
        reverse("manage_position_edit", args=[position.pk]), form_data(position, slots="1")
    )
    assert response.status_code == 200
    assert "2 people are registered or holding offers" in response.content.decode()
    position.refresh_from_db()
    assert position.slots == 3


def test_warning_when_registrations_exist(client, coordinator, volunteer, make_position):
    position = make_position()
    services.register(volunteer, position)
    client.force_login(coordinator)
    content = client.get(reverse("manage_position_edit", args=[position.pk])).content.decode()
    assert "1 person is registered for this position" in content


def test_raising_slots_offers_to_waitlist(client, coordinator, make_volunteer, make_position):
    position = make_position(slots=1)
    services.register(make_volunteer(1), position)
    waiter = services.register(make_volunteer(2), position)
    client.force_login(coordinator)
    client.post(reverse("manage_position_edit", args=[position.pk]), form_data(position, slots="2"))
    waiter.refresh_from_db()
    assert waiter.status == "offered"


def test_reinstating_event_processes_waitlists(client, coordinator, make_volunteer, make_position):
    position = make_position(slots=1)
    holder = services.register(make_volunteer(1), position)
    waiter = services.register(make_volunteer(2), position)
    position.event.cancel()
    services.remove(holder)  # no offers while cancelled
    waiter.refresh_from_db()
    assert waiter.status == "waitlisted"
    client.force_login(coordinator)
    client.post(reverse("manage_event_action", args=[position.event_id, "reinstate"]))
    waiter.refresh_from_db()
    assert waiter.status == "offered"


def test_restoring_event_processes_waitlists(client, coordinator, make_volunteer, make_position):
    position = make_position(slots=1)
    holder = services.register(make_volunteer(1), position)
    waiter = services.register(make_volunteer(2), position)
    position.event.archive()
    services.remove(holder)
    client.force_login(coordinator)
    client.post(reverse("manage_event_action", args=[position.event_id, "restore"]))
    waiter.refresh_from_db()
    assert waiter.status == "offered"
