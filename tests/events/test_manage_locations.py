import pytest
from django.urls import reverse

from events.models import Location

pytestmark = pytest.mark.django_db

VALID = {
    "name": "Library",
    "address_line1": "700 Boylston St",
    "address_line2": "",
    "city": "Boston",
    "region": "MA",
    "postal_code": "02116",
    "country": "USA",
    "notes": "",
    "map_url": "",
    "latitude": "",
    "longitude": "",
}


def urls(location):
    return [
        reverse("manage_locations"),
        reverse("manage_location_new"),
        reverse("manage_location_edit", args=[location.pk]),
        reverse("manage_location_delete", args=[location.pk]),
    ]


def test_anonymous_redirected_to_login(client, location):
    for url in urls(location):
        response = client.get(url)
        assert response.status_code == 302
        assert response.url.startswith(reverse("account_login"))


def test_volunteer_forbidden(client, complete_user, location):
    client.force_login(complete_user())
    for url in urls(location):
        assert client.get(url).status_code == 403


@pytest.mark.parametrize("user_fixture", ["coordinator", "org_admin"])
def test_staff_allowed(client, request, location, user_fixture):
    client.force_login(request.getfixturevalue(user_fixture))
    for url in urls(location):
        assert client.get(url).status_code == 200


def test_pages_load_manage_assets(client, coordinator, location):
    client.force_login(coordinator)
    content = client.get(reverse("manage_locations")).content.decode()
    assert "dist/manage.js" in content
    assert "dist/manage.css" in content


def test_create_location(client, coordinator):
    client.force_login(coordinator)
    response = client.post(reverse("manage_location_new"), VALID)
    assert response.status_code == 302
    assert response.url == reverse("manage_locations")
    assert Location.objects.filter(name="Library").exists()


def test_coordinates_need_both(client, coordinator):
    client.force_login(coordinator)
    response = client.post(reverse("manage_location_new"), {**VALID, "latitude": "42.35"})
    assert response.status_code == 200
    assert "Enter both latitude and longitude" in response.content.decode()


def test_edit_location(client, coordinator, location):
    client.force_login(coordinator)
    client.post(reverse("manage_location_edit", args=[location.pk]), {**VALID, "name": "Renamed"})
    location.refresh_from_db()
    assert location.name == "Renamed"


def test_delete_unused_location(client, coordinator, location):
    client.force_login(coordinator)
    response = client.post(reverse("manage_location_delete", args=[location.pk]))
    assert response.status_code == 302
    assert not Location.objects.filter(pk=location.pk).exists()


def test_delete_used_location_is_refused(client, coordinator, location, make_event):
    event = make_event(title="Uses it")
    client.force_login(coordinator)

    page = client.get(reverse("manage_location_delete", args=[location.pk])).content.decode()
    response = client.post(reverse("manage_location_delete", args=[location.pk]))

    assert "Uses it" in page
    assert response.status_code == 200
    assert Location.objects.filter(pk=location.pk).exists()
    assert event.title in response.content.decode()


def test_delete_location_used_only_by_a_position_is_refused(
    client, coordinator, location, make_event
):
    venue = Location.objects.create(
        name="Gym",
        address_line1="2 School St",
        city="Boston",
        region="MA",
        postal_code="02120",
        country="USA",
    )
    event = make_event()
    event.positions.update(location=venue)
    client.force_login(coordinator)
    client.post(reverse("manage_location_delete", args=[venue.pk]))
    assert Location.objects.filter(pk=venue.pk).exists()


def test_delete_page_lists_positions_using_location(client, coordinator, make_event):
    venue = Location.objects.create(
        name="Gym",
        address_line1="2 School St",
        city="Boston",
        region="MA",
        postal_code="02120",
        country="USA",
    )
    event = make_event(title="Field day", positions=((24, 1), (30, 1)))
    second = event.positions.all()[1]
    second.location = venue
    second.save()
    client.force_login(coordinator)

    page = client.get(reverse("manage_location_delete", args=[venue.pk])).content.decode()

    assert "Shift 2" in page
    assert reverse("manage_position_edit", args=[second.pk]) in page
