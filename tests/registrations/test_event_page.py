import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from organization.models import SiteSettings
from registrations import services

pytestmark = pytest.mark.django_db


def page(client, position):
    return client.get(position.event.get_absolute_url()).content.decode()


def test_spots_left_and_register_button(client, volunteer, make_position):
    position = make_position(slots=3)
    services.register(volunteer, position)
    content = page(client, position)
    assert "2 of 3 spots left" in content
    assert reverse("register", args=[position.pk]) in content


def test_full_shows_waitlist(client, make_volunteer, make_position):
    position = make_position(slots=1)
    services.register(make_volunteer(1), position)
    services.register(make_volunteer(2), position)
    content = page(client, position)
    assert "Full · 1 on the waitlist" in content
    assert "Join waitlist" in content


def test_registered_visitor(client, volunteer, make_position):
    position = make_position()
    registration = services.register(volunteer, position)
    client.force_login(volunteer)
    content = page(client, position)
    assert "You're registered" in content  # template text, not an escaped variable
    assert reverse("registration", args=[registration.pk]) in content


def test_waitlisted_visitor_sees_place(client, make_volunteer, make_position):
    position = make_position(slots=1)
    services.register(make_volunteer(2), position)
    services.register(make_volunteer(3), position)
    volunteer = make_volunteer(1)
    services.register(volunteer, position)
    client.force_login(volunteer)
    assert "#2 on the waitlist" in page(client, position)


def test_offered_visitor_sees_accept(client, make_volunteer, make_position):
    position = make_position(slots=1)
    holder = services.register(make_volunteer(2), position)
    volunteer = make_volunteer(1)
    waiter = services.register(volunteer, position)
    services.cancel(holder)
    client.force_login(volunteer)
    content = page(client, position)
    assert "A spot opened up!" in content
    assert reverse("registration_accept", args=[waiter.pk]) in content


def test_registration_closed_note(client, make_position):
    site_settings = SiteSettings.load()
    site_settings.registration_closes_hours_before = 72
    site_settings.save()
    position = make_position(starts_in_hours=48)
    content = page(client, position)
    assert "Registration is closed" in content
    assert reverse("register", args=[position.pk]) not in content


def test_cancelled_event_has_no_register_button(client, make_position):
    position = make_position(status="cancelled")
    assert reverse("register", args=[position.pk]) not in page(client, position)


def test_query_count_independent_of_position_count(client, volunteer, make_position):
    first = make_position(title="A")
    event = first.event
    client.force_login(volunteer)

    def count():
        with CaptureQueriesContext(connection) as queries:
            client.get(event.get_absolute_url())
        return len(queries)

    count()  # warm caches
    baseline = count()
    for index in range(4):
        position = make_position(title=f"B{index}", event=event, starts_in_hours=60 + index * 5)
        services.register(volunteer, position)
    assert count() == baseline
