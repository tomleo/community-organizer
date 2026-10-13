from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from events.models import Position
from organization.models import SiteSettings
from registrations import services
from registrations.models import Registration
from registrations.services import GuestData, RegistrationError

pytestmark = pytest.mark.django_db


def settings_with(**values):
    site_settings = SiteSettings.load()
    for name, value in values.items():
        setattr(site_settings, name, value)
    site_settings.save()


# Waitlisted volunteers can always leave: the cancellation cutoff protects held spots only.


def test_waitlisted_can_cancel_after_cutoff(make_volunteer, make_position):
    settings_with(cancellation_closes_hours_before=72)
    position = make_position(slots=1, starts_in_hours=48)
    services.register(make_volunteer(2), position)
    waiter = services.register(make_volunteer(1), position)

    services.cancel(waiter)

    waiter.refresh_from_db()
    assert waiter.status == "cancelled"


def test_cancel_page_open_for_waitlisted_after_cutoff(client, make_volunteer, make_position):
    settings_with(cancellation_closes_hours_before=72)
    position = make_position(slots=1, starts_in_hours=48)
    services.register(make_volunteer(2), position)
    waiter = services.register(make_volunteer(1), position)
    client.force_login(waiter.volunteer)
    content = client.get(reverse("registration_cancel", args=[waiter.pk])).content.decode()
    assert "Cancellation has closed" not in content


# Editing respects the start time and both cutoffs.


def test_no_edits_after_start(volunteer, make_position):
    registration = services.register(volunteer, make_position(starts_in_hours=48))
    Position.objects.filter(pk=registration.position_id).update(
        starts_at=timezone.now() - timedelta(hours=1)
    )
    with pytest.raises(RegistrationError, match="already started"):
        services.update(registration, [], "Late note")


def test_adding_guests_after_registration_cutoff_refused(volunteer, make_position):
    settings_with(max_guests=2)
    registration = services.register(volunteer, make_position(slots=5, starts_in_hours=48))
    settings_with(registration_closes_hours_before=72)
    with pytest.raises(RegistrationError, match="Registration has closed"):
        services.update(registration, [GuestData("Sam", "Lee")], "")


def test_removing_guests_after_cancellation_cutoff_refused(volunteer, make_position):
    settings_with(max_guests=2)
    registration = services.register(
        volunteer, make_position(slots=5, starts_in_hours=48), guests=[GuestData("Sam", "Lee")]
    )
    settings_with(cancellation_closes_hours_before=72)
    with pytest.raises(RegistrationError, match="Cancellation has closed"):
        services.update(registration, [], "")


def test_comment_only_edit_allowed_after_cutoffs(volunteer, make_position):
    registration = services.register(volunteer, make_position(starts_in_hours=48))
    settings_with(registration_closes_hours_before=72, cancellation_closes_hours_before=72)
    services.update(registration, [], "Running late")
    registration.refresh_from_db()
    assert registration.comments == "Running late"


def test_manage_page_not_editable_after_start(client, volunteer, make_position):
    registration = Registration.objects.create(
        volunteer=volunteer, position=make_position(starts_in_hours=-48), status="registered"
    )
    client.force_login(volunteer)
    content = client.get(reverse("registration", args=[registration.pk])).content.decode()
    assert "Save changes" not in content


# Turning guests off must not delete guests already registered.


def test_turning_guests_off_keeps_existing_guests(client, volunteer, make_position):
    settings_with(max_guests=2)
    registration = services.register(
        volunteer, make_position(slots=5), guests=[GuestData("Sam", "Lee")]
    )
    settings_with(max_guests=0)
    client.force_login(volunteer)
    client.post(reverse("registration", args=[registration.pk]), {"comments": "Just a note"})
    registration.refresh_from_db()
    assert registration.comments == "Just a note"
    assert registration.party_size == 2


# A party bigger than the whole position can never get in, so don't waitlist it.


def test_party_larger_than_position_refused(volunteer, make_position):
    settings_with(max_guests=3)
    with pytest.raises(RegistrationError, match="only has 2 spots"):
        services.register(
            volunteer,
            make_position(slots=2),
            guests=[GuestData("A", "B"), GuestData("C", "D")],
        )
    assert not Registration.objects.exists()


def test_waitlisted_party_cannot_grow_beyond_position(make_volunteer, make_position):
    settings_with(max_guests=3)
    position = make_position(slots=2)
    services.register(make_volunteer(2), position)
    services.register(make_volunteer(3), position)
    waiter = services.register(make_volunteer(1), position)
    with pytest.raises(RegistrationError, match="only has 2 spots"):
        services.update(waiter, [GuestData("A", "B"), GuestData("C", "D")], "")
