from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse

from events.models import Location, Position
from organization.models import SiteSettings

pytestmark = pytest.mark.django_db

VALID = {
    "title": "Sorting",
    "starts_at": "2030-11-08T09:00",
    "ends_at": "2030-11-08T12:00",
    "slots": "4",
    "location": "",
    "description": "<div>Wear closed shoes</div>",
}


def test_create_position(client, coordinator, make_event):
    event = make_event(status="draft", positions=())
    client.force_login(coordinator)
    response = client.post(reverse("manage_position_new", args=[event.pk]), VALID)
    assert response.url == reverse("manage_event", args=[event.pk])
    position = event.positions.get()
    assert position.title == "Sorting"
    assert position.location is None
    assert position.effective_location == event.location


def test_times_are_in_site_time_zone(client, coordinator, make_event):
    site_settings = SiteSettings.load()
    site_settings.time_zone = "America/Chicago"
    site_settings.save()
    event = make_event(status="draft", positions=())
    client.force_login(coordinator)
    client.post(reverse("manage_position_new", args=[event.pk]), VALID)
    position = event.positions.get()
    assert position.starts_at == datetime(2030, 11, 8, 9, 0, tzinfo=ZoneInfo("America/Chicago"))


def test_end_must_be_after_start(client, coordinator, make_event):
    event = make_event(status="draft", positions=())
    client.force_login(coordinator)
    response = client.post(
        reverse("manage_position_new", args=[event.pk]), {**VALID, "ends_at": "2030-11-08T08:00"}
    )
    assert response.status_code == 200
    assert "The end must be after the start." in response.content.decode()
    assert not event.positions.exists()


def test_position_with_other_location(client, coordinator, make_event):
    gym = Location.objects.create(
        name="Gym",
        address_line1="2 School St",
        city="Boston",
        region="MA",
        postal_code="02120",
        country="USA",
    )
    event = make_event(status="draft", positions=())
    client.force_login(coordinator)
    client.post(reverse("manage_position_new", args=[event.pk]), {**VALID, "location": gym.pk})
    assert event.positions.get().location == gym


def test_edit_position(client, coordinator, make_event):
    event = make_event()
    position = event.positions.get()
    client.force_login(coordinator)
    client.post(reverse("manage_position_edit", args=[position.pk]), {**VALID, "title": "Greeter"})
    position.refresh_from_db()
    assert position.title == "Greeter"


def test_delete_position_on_draft(client, coordinator, make_event):
    event = make_event(status="draft")
    position = event.positions.get()
    client.force_login(coordinator)
    assert client.get(reverse("manage_position_delete", args=[position.pk])).status_code == 200
    response = client.post(reverse("manage_position_delete", args=[position.pk]))
    assert response.url == reverse("manage_event", args=[event.pk])
    assert not Position.objects.filter(pk=position.pk).exists()


def test_cannot_delete_position_of_published_event(client, coordinator, make_event):
    position = make_event(status="published").positions.get()
    client.force_login(coordinator)
    response = client.post(reverse("manage_position_delete", args=[position.pk]), follow=True)
    assert "be deleted after the event is published" in response.content.decode()
    assert Position.objects.filter(pk=position.pk).exists()


def test_hub_links(client, coordinator, make_event):
    draft = make_event(status="draft")
    published = make_event(status="published")
    client.force_login(coordinator)
    draft_page = client.get(reverse("manage_event", args=[draft.pk])).content.decode()
    published_page = client.get(reverse("manage_event", args=[published.pk])).content.decode()
    assert reverse("manage_position_new", args=[draft.pk]) in draft_page
    assert reverse("manage_position_delete", args=[draft.positions.get().pk]) in draft_page
    assert (
        reverse("manage_position_delete", args=[published.positions.get().pk]) not in published_page
    )


def test_volunteers_forbidden(client, complete_user, make_event):
    event = make_event(status="draft")
    position = event.positions.get()
    client.force_login(complete_user())
    assert client.get(reverse("manage_position_new", args=[event.pk])).status_code == 403
    assert client.get(reverse("manage_position_edit", args=[position.pk])).status_code == 403
    assert client.post(reverse("manage_position_delete", args=[position.pk])).status_code == 403
