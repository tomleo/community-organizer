from datetime import timedelta

import pytest
from django.utils import timezone

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


def test_register_when_spots_left(volunteer, make_position):
    registration = services.register(volunteer, make_position(slots=2), comments="Hi")
    assert registration.status == "registered"
    assert registration.comments == "Hi"
    assert registration.waitlisted_at is None


def test_full_position_waitlists(make_volunteer, make_position):
    position = make_position(slots=1)
    services.register(make_volunteer(1), position)
    second = services.register(make_volunteer(2), position)
    assert second.status == "waitlisted"
    assert second.waitlisted_at is not None
    assert services.waitlist_place(second) == 1


def test_guests_take_spots(make_volunteer, make_position):
    settings_with(max_guests=3)
    position = make_position(slots=3)
    first = services.register(make_volunteer(1), position, guests=[GuestData("Sam", "Lee")])
    assert first.status == "registered"
    assert services.spots_taken(position) == 2
    second = services.register(make_volunteer(2), position, guests=[GuestData("A", "B")])
    assert second.status == "waitlisted"
    assert list(second.guests.values_list("first_name", flat=True)) == ["A"]


def test_smaller_party_is_not_blocked_by_big_waitlisted_party(make_volunteer, make_position):
    settings_with(max_guests=3)
    position = make_position(slots=3)
    services.register(make_volunteer(1), position)
    big = services.register(
        make_volunteer(2), position, guests=[GuestData("A", "B"), GuestData("C", "D")]
    )
    assert big.status == "waitlisted"
    assert services.register(make_volunteer(3), position).status == "registered"


def test_guests_refused_when_turned_off(volunteer, make_position):
    with pytest.raises(RegistrationError, match="Guests aren't allowed"):
        services.register(volunteer, make_position(), guests=[GuestData("Sam", "Lee")])


def test_guest_limit(volunteer, make_position):
    settings_with(max_guests=1)
    with pytest.raises(RegistrationError, match="at most 1 guest"):
        services.register(
            volunteer, make_position(slots=5), guests=[GuestData("A", "B"), GuestData("C", "D")]
        )


def test_already_registered(volunteer, make_position):
    position = make_position()
    services.register(volunteer, position)
    with pytest.raises(RegistrationError, match="already registered"):
        services.register(volunteer, position)


@pytest.mark.parametrize("status", ["draft", "cancelled"])
def test_not_open_unless_published(volunteer, make_position, status):
    with pytest.raises(RegistrationError, match="isn't open"):
        services.register(volunteer, make_position(status=status))


def test_not_open_when_archived(volunteer, make_position):
    position = make_position()
    position.event.archive()
    with pytest.raises(RegistrationError, match="isn't open"):
        services.register(volunteer, position)


def test_not_open_after_start(volunteer, make_position):
    with pytest.raises(RegistrationError, match="isn't open"):
        services.register(volunteer, make_position(starts_in_hours=-1))


def test_registration_cutoff(volunteer, make_position):
    settings_with(registration_closes_hours_before=72)
    with pytest.raises(RegistrationError, match="Registration has closed"):
        services.register(volunteer, make_position(starts_in_hours=48))


def test_staff_bypass_cutoff_profile_and_rate_limit(make_user, make_position):
    settings_with(registration_closes_hours_before=72)
    incomplete = make_user("new@example.org")
    assert services.register(incomplete, make_position(), by_staff=True).status == "registered"


def test_incomplete_profile_refused(make_user, make_position):
    with pytest.raises(RegistrationError, match="complete your profile"):
        services.register(make_user("new@example.org"), make_position())


def test_overlap_refused(volunteer, make_position):
    services.register(volunteer, make_position(starts_in_hours=48, hours=3))
    with pytest.raises(RegistrationError, match="overlaps"):
        services.register(volunteer, make_position(starts_in_hours=50, hours=3))


def test_overlap_applies_to_waitlist_places(make_volunteer, make_position):
    full = make_position(slots=1, starts_in_hours=48)
    services.register(make_volunteer(2), full)
    volunteer = make_volunteer(1)
    assert services.register(volunteer, full).status == "waitlisted"
    with pytest.raises(RegistrationError, match="overlaps"):
        services.register(volunteer, make_position(starts_in_hours=49))


def test_overlap_refused_for_staff_too(volunteer, make_position):
    services.register(volunteer, make_position(starts_in_hours=48, hours=3))
    with pytest.raises(RegistrationError, match="overlaps"):
        services.register(volunteer, make_position(starts_in_hours=49), by_staff=True)


def test_back_to_back_is_not_overlap(volunteer, make_position):
    first = make_position(starts_in_hours=48, hours=3)
    second = make_position(starts_in_hours=51, hours=2)
    services.register(volunteer, first)
    assert services.register(volunteer, second).status == "registered"


def test_cancelled_registration_does_not_count_as_overlap(volunteer, make_position):
    first = services.register(volunteer, make_position(starts_in_hours=48))
    Registration.objects.filter(pk=first.pk).update(status="cancelled")
    assert services.register(volunteer, make_position(starts_in_hours=49)).status == "registered"


def test_rate_limit(volunteer, make_position):
    for index in range(services.RATE_LIMIT):
        Registration.objects.create(
            volunteer=volunteer,
            position=make_position(starts_in_hours=100 + index * 10),
            status="cancelled",
        )
    with pytest.raises(RegistrationError, match="try again"):
        services.register(volunteer, make_position(starts_in_hours=500))


def test_update_comments_and_guests(volunteer, make_position):
    settings_with(max_guests=2)
    registration = services.register(volunteer, make_position(slots=3))
    services.update(registration, [GuestData("Sam", "Lee", "Friend")], "Updated")
    registration.refresh_from_db()
    assert registration.comments == "Updated"
    assert registration.party_size == 2
    assert registration.guests.get().relationship == "Friend"


def test_update_growth_beyond_capacity_refused(make_volunteer, make_position):
    settings_with(max_guests=3)
    position = make_position(slots=2)
    registration = services.register(make_volunteer(1), position)
    services.register(make_volunteer(2), position)
    with pytest.raises(RegistrationError, match="Only 0 spots left"):
        services.update(registration, [GuestData("A", "B")], "")
    assert registration.party_size == 1


def test_update_refused_while_offered(volunteer, make_position):
    registration = services.register(volunteer, make_position())
    Registration.objects.filter(pk=registration.pk).update(
        status="offered", offer_expires_at=timezone.now() + timedelta(hours=1)
    )
    with pytest.raises(RegistrationError, match="Accept or decline"):
        services.update(registration, [], "")


def test_update_refused_when_not_active(volunteer, make_position):
    registration = services.register(volunteer, make_position())
    Registration.objects.filter(pk=registration.pk).update(status="cancelled")
    with pytest.raises(RegistrationError, match="no longer active"):
        services.update(registration, [], "")
