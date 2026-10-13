import pytest
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse

from organization.permissions import can_manage, management_links

pytestmark = pytest.mark.django_db


def labels(user):
    return [link["label"] for link in management_links(user)]


def test_volunteer_and_anonymous_have_no_links(complete_user):
    assert labels(AnonymousUser()) == []
    assert labels(complete_user()) == []
    assert can_manage(complete_user("other@example.org")) is False


def test_coordinator_links(coordinator):
    assert labels(coordinator) == ["Events", "Locations", "Volunteers", "Messages"]
    assert can_manage(coordinator) is True


def test_admin_links(org_admin):
    assert labels(org_admin) == [
        "Events",
        "Locations",
        "Volunteers",
        "Messages",
        "Site settings",
        "Profile questions",
        "Email log",
    ]


def test_links_have_urls(org_admin):
    assert [link["url"] for link in management_links(org_admin)] == [
        reverse("manage_events"),
        reverse("manage_locations"),
        reverse("manage_volunteers"),
        reverse("manage_messages"),
        reverse("manage_settings"),
        reverse("manage_questions"),
        reverse("manage_emails"),
    ]


def test_navbar_dropdown(client, coordinator):
    client.force_login(coordinator)
    content = client.get(reverse("home")).content.decode()
    assert 'data-bs-toggle="dropdown"' in content
    assert reverse("manage_events") in content
    assert reverse("manage_settings") not in content
