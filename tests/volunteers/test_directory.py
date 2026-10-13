from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from organization.roles import Role, set_role
from registrations.models import Guest, Registration
from volunteers.services import hours_for, volunteer_stats

pytestmark = pytest.mark.django_db


def past_registration(volunteer, make_position, hours=3, attendance="attended", guests=0):
    position = make_position(starts_in_hours=-48, hours=hours)
    registration = Registration.objects.create(
        volunteer=volunteer, position=position, status="registered", attendance=attendance
    )
    for index in range(guests):
        Guest.objects.create(registration=registration, first_name=f"G{index}", last_name="X")
    return registration


def test_hours_count_attended_only(volunteer, make_position):
    past_registration(volunteer, make_position, hours=3)
    past_registration(volunteer, make_position, hours=2, attendance="no_show")
    past_registration(volunteer, make_position, hours=4, attendance="")
    assert hours_for(volunteer) == timedelta(hours=3)


def test_hours_not_multiplied_by_guests_or_registrations(
    volunteer, make_position, django_user_model
):
    past_registration(volunteer, make_position, hours=3, guests=2)
    past_registration(volunteer, make_position, hours=2)
    stats = volunteer_stats(django_user_model.objects.filter(pk=volunteer.pk)).get()
    assert stats.hours == timedelta(hours=5)
    assert stats.attended_count == 2
    assert stats.no_show_count == 0


def test_has_upcoming_and_last_shift(volunteer, make_position, django_user_model):
    past = past_registration(volunteer, make_position)
    Registration.objects.create(volunteer=volunteer, position=make_position(), status="waitlisted")
    stats = volunteer_stats(django_user_model.objects.filter(pk=volunteer.pk)).get()
    assert stats.has_upcoming is True
    assert stats.last_shift_at == past.position.starts_at


def directory(client, **params):
    return client.get(reverse("manage_volunteers"), params).content.decode()


def test_permissions(client, volunteer, coordinator, org_admin):
    url = reverse("manage_volunteers")
    assert client.get(url).status_code == 302
    client.force_login(volunteer)
    assert client.get(url).status_code == 403
    for user in (coordinator, org_admin):
        client.force_login(user)
        assert client.get(url).status_code == 200


def test_search_filter_sort(client, coordinator, make_volunteer, make_position):
    ada, grace = make_volunteer(1), make_volunteer(2)
    grace.profile.first_name, grace.profile.last_name = "Grace", "Hopper"
    grace.profile.save()
    past_registration(grace, make_position, hours=5)
    set_role(ada, Role.COORDINATOR)
    client.force_login(coordinator)

    assert "vol2@example.org" in directory(client, q="hopper")
    assert "vol1@example.org" not in directory(client, q="hopper")
    coordinators = directory(client, role="coordinator")
    assert "vol1@example.org" in coordinators and "vol2@example.org" not in coordinators
    by_hours = directory(client, sort="hours")
    assert by_hours.index("vol2@example.org") < by_hours.index("vol1@example.org")
    assert "5" in by_hours


def test_upcoming_filter(client, coordinator, make_volunteer, make_position):
    busy, idle = make_volunteer(1), make_volunteer(2)
    Registration.objects.create(volunteer=busy, position=make_position(), status="registered")
    client.force_login(coordinator)
    content = directory(client, upcoming="1")
    assert "vol1@example.org" in content and "vol2@example.org" not in content
    assert idle


def test_anonymized_hidden(client, coordinator, volunteer):
    volunteer.profile.deleted_at = timezone.now()
    volunteer.profile.save()
    client.force_login(coordinator)
    assert "vol1@example.org" not in directory(client)


def test_query_count_independent_of_rows(client, coordinator, make_volunteer, make_position):
    client.force_login(coordinator)

    def count():
        with CaptureQueriesContext(connection) as queries:
            client.get(reverse("manage_volunteers"))
        return len(queries)

    make_volunteer(1)
    count()
    baseline = count()
    for n in range(2, 7):
        past_registration(make_volunteer(n), make_position)
    assert count() == baseline


def test_menu_has_volunteers(coordinator):
    from organization.permissions import management_links

    assert "Volunteers" in [link["label"] for link in management_links(coordinator)]
