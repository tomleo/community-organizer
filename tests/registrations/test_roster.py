import pytest
from django.urls import reverse

from registrations import services
from registrations.models import Registration

pytestmark = pytest.mark.django_db


def roster_url(position):
    return reverse("manage_roster", args=[position.pk])


def test_roster_permissions(client, volunteer, coordinator, org_admin, make_position):
    position = make_position()
    assert client.get(roster_url(position)).status_code == 302
    client.force_login(volunteer)
    assert client.get(roster_url(position)).status_code == 403
    for user in (coordinator, org_admin):
        client.force_login(user)
        assert client.get(roster_url(position)).status_code == 200


def test_roster_contents(client, coordinator, make_volunteer, make_position):
    position = make_position(slots=1)
    services.register(make_volunteer(1), position, comments="Allergic to cats")
    services.register(make_volunteer(2), position)
    client.force_login(coordinator)
    content = client.get(roster_url(position)).content.decode()
    assert "1 of 1 taken, 0 open, 1 waiting" in content
    assert "vol1@example.org" in content
    assert "617-555-0100" in content
    assert "Allergic to cats" in content
    assert "vol2@example.org" in content


def test_remove(client, coordinator, make_volunteer, make_position):
    position = make_position(slots=1)
    holder = services.register(make_volunteer(1), position)
    waiter = services.register(make_volunteer(2), position)
    client.force_login(coordinator)
    assert client.get(reverse("manage_registration_remove", args=[holder.pk])).status_code == 200
    client.post(reverse("manage_registration_remove", args=[holder.pk]))
    holder.refresh_from_db()
    waiter.refresh_from_db()
    assert holder.status == "removed"
    assert waiter.status == "offered"


def test_promote(client, coordinator, make_volunteer, make_position):
    position = make_position(slots=1)
    services.register(make_volunteer(1), position)
    waiter = services.register(make_volunteer(2), position)
    position.slots = 2
    position.save()
    client.force_login(coordinator)
    response = client.post(reverse("manage_registration_promote", args=[waiter.pk]), follow=True)
    waiter.refresh_from_db()
    assert waiter.status == "registered"
    assert "Moved up" in response.content.decode()


def test_promote_error_message(client, coordinator, make_volunteer, make_position):
    position = make_position(slots=1)
    services.register(make_volunteer(1), position)
    waiter = services.register(make_volunteer(2), position)
    client.force_login(coordinator)
    response = client.post(reverse("manage_registration_promote", args=[waiter.pk]), follow=True)
    assert "fit in the open spots" in response.content.decode()


def test_add_volunteer(client, coordinator, make_user, make_position):
    position = make_position()
    walk_in = make_user("walkin@example.org")  # incomplete profile is fine for staff adds
    client.force_login(coordinator)
    response = client.post(
        reverse("manage_roster_add", args=[position.pk]),
        {"email": "WALKIN@example.org", "comments": ""},
        follow=True,
    )
    assert "Added walkin@example.org" in response.content.decode()
    assert Registration.objects.get(volunteer=walk_in).status == "registered"


def test_add_unknown_email(client, coordinator, make_position):
    position = make_position()
    client.force_login(coordinator)
    response = client.post(
        reverse("manage_roster_add", args=[position.pk]),
        {"email": "nobody@example.org", "comments": ""},
        follow=True,
    )
    assert "No volunteer with that email" in response.content.decode()


def test_actions_forbidden_for_volunteers(client, volunteer, make_volunteer, make_position):
    position = make_position()
    registration = services.register(make_volunteer(2), position)
    client.force_login(volunteer)
    assert (
        client.post(reverse("manage_registration_remove", args=[registration.pk])).status_code
        == 403
    )
    assert (
        client.post(reverse("manage_registration_promote", args=[registration.pk])).status_code
        == 403
    )
    assert (
        client.post(
            reverse("manage_roster_add", args=[position.pk]), {"email": "x@example.org"}
        ).status_code
        == 403
    )


def test_hub_shows_capacity_and_roster_link(client, coordinator, volunteer, make_position):
    position = make_position(slots=4)
    services.register(volunteer, position)
    client.force_login(coordinator)
    content = client.get(reverse("manage_event", args=[position.event_id])).content.decode()
    assert "1 / 4" in content
    assert roster_url(position) in content
