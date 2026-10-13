import pytest
from django.urls import reverse

from events.models import Event

pytestmark = pytest.mark.django_db


def test_list_requires_permission(client, complete_user):
    assert client.get(reverse("manage_events")).status_code == 302
    client.force_login(complete_user())
    assert client.get(reverse("manage_events")).status_code == 403


@pytest.mark.parametrize("name", ["manage_event", "manage_event_edit"])
def test_event_pages_require_permission(client, complete_user, make_event, name):
    url = reverse(name, args=[make_event().pk])
    client.force_login(complete_user())
    assert client.get(url).status_code == 403


def test_list_tabs_and_search(client, coordinator, make_event):
    make_event(title="Spring cleanup", status="draft", positions=())
    make_event(title="Food drive")
    make_event(title="Old drive", positions=((-48, 1),))
    client.force_login(coordinator)

    upcoming = client.get(reverse("manage_events")).content.decode()
    drafts = client.get(reverse("manage_events") + "?tab=drafts").content.decode()
    past = client.get(reverse("manage_events") + "?tab=past").content.decode()
    search = client.get(reverse("manage_events") + "?tab=past&q=drive").content.decode()

    assert "Spring cleanup" in upcoming and "Food drive" in upcoming and "Old drive" not in upcoming
    assert "Spring cleanup" in drafts and "Food drive" not in drafts
    assert "Old drive" in past
    assert "Old drive" in search


def test_pagination_keeps_tab_and_search(client, coordinator, make_event):
    for index in range(26):
        make_event(title=f"Drive {index:02d}", positions=((-(index + 2), 1),))
    client.force_login(coordinator)
    content = client.get(reverse("manage_events") + "?tab=past&q=Drive").content.decode()
    assert "?tab=past&amp;q=Drive&amp;page=2" in content


def test_create_event_makes_a_draft(client, coordinator, location):
    client.force_login(coordinator)
    response = client.post(
        reverse("manage_event_new"),
        {
            "title": "Book sale",
            "location": location.pk,
            "description": "<div>Hi</div><script>x()</script>",
            "resources_url": "",
        },
    )
    event = Event.objects.get(title="Book sale")
    assert response.url == reverse("manage_event", args=[event.pk])
    assert event.status == Event.Status.DRAFT
    assert event.description == "<div>Hi</div>"


def test_edit_event(client, coordinator, make_event, location):
    event = make_event()
    client.force_login(coordinator)
    client.post(
        reverse("manage_event_edit", args=[event.pk]),
        {
            "title": "Renamed",
            "location": location.pk,
            "description": "",
            "resources_url": "https://example.org",
        },
    )
    event.refresh_from_db()
    assert event.title == "Renamed"
    assert event.resources_url == "https://example.org"


def test_hub_shows_publish_disabled_without_positions(client, coordinator, make_event):
    event = make_event(status="draft", positions=())
    client.force_login(coordinator)
    content = client.get(reverse("manage_event", args=[event.pk])).content.decode()
    assert "Add a position first" in content


def action(client, event, name):
    return client.post(reverse("manage_event_action", args=[event.pk, name]), follow=True)


def test_publish_without_positions_shows_error(client, coordinator, make_event):
    event = make_event(status="draft", positions=())
    client.force_login(coordinator)
    response = action(client, event, "publish")
    assert "Add a position before publishing." in response.content.decode()
    event.refresh_from_db()
    assert event.status == Event.Status.DRAFT


def test_status_actions(client, coordinator, make_event):
    event = make_event(status="draft")
    client.force_login(coordinator)
    for name, field, expected in [
        ("publish", "status", "published"),
        ("cancel", "status", "cancelled"),
        ("reinstate", "status", "published"),
        ("pin", "pinned", True),
        ("unpin", "pinned", False),
    ]:
        response = action(client, event, name)
        assert response.status_code == 200
        event.refresh_from_db()
        assert getattr(event, field) == expected
    action(client, event, "archive")
    event.refresh_from_db()
    assert event.archived_at is not None
    action(client, event, "restore")
    event.refresh_from_db()
    assert event.archived_at is None


def test_unknown_action_404(client, coordinator, make_event):
    client.force_login(coordinator)
    response = client.post(reverse("manage_event_action", args=[make_event().pk, "explode"]))
    assert response.status_code == 404


def test_actions_require_post(client, coordinator, make_event):
    client.force_login(coordinator)
    response = client.get(reverse("manage_event_action", args=[make_event().pk, "publish"]))
    assert response.status_code == 405


def test_actions_forbidden_for_volunteers(client, complete_user, make_event):
    event = make_event(status="draft")
    client.force_login(complete_user())
    assert (
        client.post(reverse("manage_event_action", args=[event.pk, "publish"])).status_code == 403
    )


def test_bulk_archive(client, coordinator, make_event):
    first, second, keep = make_event(title="a"), make_event(title="b"), make_event(title="c")
    client.force_login(coordinator)
    response = client.post(
        reverse("manage_events_archive"), {"ids": [first.pk, second.pk]}, follow=True
    )
    assert "Archived 2 events." in response.content.decode()
    assert Event.objects.filter(archived_at__isnull=False).count() == 2
    keep.refresh_from_db()
    assert keep.archived_at is None


def test_public_page_edit_link_goes_to_hub(client, coordinator, make_event):
    event = make_event()
    client.force_login(coordinator)
    content = client.get(event.get_absolute_url()).content.decode()
    assert reverse("manage_event", args=[event.pk]) in content
