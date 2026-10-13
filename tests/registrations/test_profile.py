import pytest
from django.urls import reverse

from registrations import services
from registrations.models import Registration

pytestmark = pytest.mark.django_db


def profile(client, user):
    client.force_login(user)
    return client.get(reverse("profile")).content.decode()


def test_upcoming_registered_and_waitlisted(client, make_volunteer, make_position):
    volunteer = make_volunteer(1)
    services.register(volunteer, make_position(title="Sorting", slots=2))
    full = make_position(title="Greeter", slots=1, starts_in_hours=100)
    services.register(make_volunteer(2), full)
    services.register(volunteer, full)
    content = profile(client, volunteer)
    assert "Upcoming" in content
    assert "Sorting" in content
    assert "Greeter" in content
    assert "#1 on the waitlist" in content


def test_offers_section(client, make_volunteer, make_position):
    position = make_position(title="Driver", slots=1)
    holder = services.register(make_volunteer(2), position)
    volunteer = make_volunteer(1)
    waiter = services.register(volunteer, position)
    services.cancel(holder)
    content = profile(client, volunteer)
    assert "Offers waiting for you" in content
    assert reverse("registration_accept", args=[waiter.pk]) in content


def test_past_section(client, volunteer, make_position):
    position = make_position(title="Old shift", starts_in_hours=-48)
    Registration.objects.create(volunteer=volunteer, position=position, status="registered")
    content = profile(client, volunteer)
    assert "Past" in content
    assert "Old shift" in content


def test_ended_registrations_hidden(client, volunteer, make_position):
    registration = services.register(volunteer, make_position(title="Dropped"))
    services.cancel(registration)
    assert "Dropped" not in profile(client, volunteer)


def test_only_own_registrations(client, make_volunteer, make_position):
    services.register(make_volunteer(2), make_position(title="Someone else's"))
    assert "Someone else" not in profile(client, make_volunteer(1))
