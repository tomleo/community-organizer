import json
import re

import pytest
from django.core.files.storage import default_storage
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from events.models import EventPhoto, Location

pytestmark = pytest.mark.django_db

JSONLD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def jsonld(response):
    return json.loads(JSONLD.search(response.content.decode()).group(1))


def test_list_shows_public_upcoming_only(client, make_event):
    make_event(title="Visible")
    make_event(title="Draft one", status="draft")
    make_event(title="Old one", positions=((-48, 1),))
    archived = make_event(title="Archived one")
    archived.archive()

    content = client.get(reverse("events")).content.decode()

    assert "Visible" in content
    assert "Draft one" not in content
    assert "Old one" not in content
    assert "Archived one" not in content


def test_past_tab(client, make_event):
    make_event(title="Old one", positions=((-48, 1),))
    make_event(title="Visible")
    content = client.get(reverse("events") + "?when=past").content.decode()
    assert "Old one" in content
    assert "Visible" not in content


def test_cancelled_badge(client, make_event):
    make_event(title="Called off", status="cancelled")
    assert "Cancelled" in client.get(reverse("events")).content.decode()


def test_pagination(client, make_event):
    for hours in range(1, 14):
        make_event(title=f"Event {hours:02d}", positions=((hours, 1),))
    first = client.get(reverse("events")).content.decode()
    second = client.get(reverse("events") + "?page=2").content.decode()
    assert "Event 12" in first and "Event 13" not in first
    assert "Event 13" in second


def test_list_query_count_does_not_grow(client, make_event, make_image_file):
    def count_queries():
        with CaptureQueriesContext(connection) as queries:
            client.get(reverse("events"))
        return len(queries)

    make_event(title="first")
    count_queries()  # warm-up: the first request also fills the site settings cache
    baseline = count_queries()
    for index in range(5):
        event = make_event(title=f"more {index}")
        EventPhoto.objects.create(event=event, image=make_image_file(), position=0)
    assert count_queries() == baseline


def test_detail_page(client, make_event):
    event = make_event(
        title="Park cleanup", positions=((24, 3), (26, 2)), description="<div>Bring gloves</div>"
    )
    content = client.get(event.get_absolute_url()).content.decode()
    assert "Park cleanup" in content
    assert "Bring gloves" in content
    assert "Shift 1" in content and "Shift 2" in content
    assert "5 spots" in content
    assert "Community Center" in content


def test_detail_shows_position_location_only_when_different(client, make_event):
    gym = Location.objects.create(
        name="Gym",
        address_line1="2 School St",
        city="Boston",
        region="MA",
        postal_code="02120",
        country="USA",
    )
    event = make_event(positions=((24, 1), (30, 1)))
    second = event.positions.all()[1]
    second.location = gym
    second.save()
    content = JSONLD.sub("", client.get(event.get_absolute_url()).content.decode())
    assert content.count("Gym") == 1


def test_draft_and_archived_404_for_public(client, make_event):
    draft = make_event(status="draft")
    archived = make_event()
    archived.archive()
    assert client.get(draft.get_absolute_url()).status_code == 404
    assert client.get(archived.get_absolute_url()).status_code == 404


def test_staff_can_preview_drafts(client, coordinator, make_event):
    draft = make_event(status="draft")
    client.force_login(coordinator)
    response = client.get(draft.get_absolute_url())
    assert response.status_code == 200
    assert "Draft — not visible to the public" in response.content.decode()


def test_cancelled_banner(client, make_event):
    event = make_event(status="cancelled")
    assert "This event has been cancelled" in client.get(event.get_absolute_url()).content.decode()


def test_photo_without_variants_falls_back_to_original(client, make_event, make_image_file):
    event = make_event()
    photo = EventPhoto.objects.create(event=event, image=make_image_file(), position=0)
    content = client.get(event.get_absolute_url()).content.decode()
    assert default_storage.url(photo.image.name) in content


def test_jsonld(client, make_event, settings):
    from organization.models import SiteSettings

    site_settings = SiteSettings.load()
    site_settings.org_name = "Neighborhood Pantry"
    site_settings.website_url = "https://pantry.example"
    site_settings.save()
    event = make_event(
        title="Food drive",
        positions=((24, 2), (48, 2)),
        description="<div>Help <strong>sort</strong></div>",
    )
    location = event.location
    location.latitude, location.longitude = 42.35, -71.06
    location.map_url = "https://maps.example/cc"
    location.save()

    data = jsonld(client.get(event.get_absolute_url()))

    assert data["@type"] == "Event"
    assert data["name"] == "Food drive"
    assert data["description"] == "Help sort"
    assert data["eventStatus"] == "https://schema.org/EventScheduled"
    assert data["eventAttendanceMode"] == "https://schema.org/OfflineEventAttendanceMode"
    assert data["url"] == "http://testserver" + event.get_absolute_url()
    assert data["organizer"] == {
        "@type": "Organization",
        "name": "Neighborhood Pantry",
        "url": "https://pantry.example",
    }
    assert data["location"]["address"]["@type"] == "PostalAddress"
    assert data["location"]["address"]["addressLocality"] == "Boston"
    assert data["location"]["geo"] == {
        "@type": "GeoCoordinates",
        "latitude": 42.35,
        "longitude": -71.06,
    }
    assert data["location"]["hasMap"] == "https://maps.example/cc"
    assert len(data["subEvent"]) == 2
    assert data["subEvent"][0]["maximumAttendeeCapacity"] == 5
    assert data["startDate"] == data["subEvent"][0]["startDate"]


def test_jsonld_cancelled_status(client, make_event):
    event = make_event(status="cancelled")
    assert (
        jsonld(client.get(event.get_absolute_url()))["eventStatus"]
        == "https://schema.org/EventCancelled"
    )


def test_jsonld_cannot_break_out_of_script(client, make_event):
    event = make_event(title="</script><script>alert(1)</script>")
    content = client.get(event.get_absolute_url()).content.decode()
    assert "<script>alert(1)" not in content
    assert (
        jsonld(client.get(event.get_absolute_url()))["name"] == "</script><script>alert(1)</script>"
    )


def test_no_jsonld_on_draft_preview(client, coordinator, make_event):
    client.force_login(coordinator)
    content = client.get(make_event(status="draft").get_absolute_url()).content.decode()
    assert "application/ld+json" not in content


def test_home_featured_events(client, make_event):
    make_event(title="Next up")
    content = client.get(reverse("home")).content.decode()
    assert "Next up" in content
    assert reverse("events") in content


def test_navbar_has_events_link(client):
    assert f'href="{reverse("events")}"' in client.get(reverse("home")).content.decode()
