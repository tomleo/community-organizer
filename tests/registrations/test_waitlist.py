from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from organization.models import SiteSettings
from registrations import services
from registrations.models import Registration
from registrations.services import GuestData, RegistrationError

pytestmark = pytest.mark.django_db


def refresh(registration):
    registration.refresh_from_db()
    return registration


def full_with_waitlist(make_volunteer, make_position, waiting=2, **position_kwargs):
    position = make_position(slots=1, **position_kwargs)
    holder = services.register(make_volunteer(1), position)
    waiters = [services.register(make_volunteer(n), position) for n in range(2, 2 + waiting)]
    return position, holder, waiters


def test_cancel_offers_spot_to_next_in_line(make_volunteer, make_position):
    position, holder, (first, second) = full_with_waitlist(make_volunteer, make_position)

    services.cancel(holder)

    assert refresh(holder).status == "cancelled"
    assert refresh(holder).ended_at is not None
    first = refresh(first)
    assert first.status == "offered"
    assert first.offer_expires_at == first.offered_at + timedelta(hours=24)
    assert refresh(second).status == "waitlisted"


def test_offer_expiry_capped_at_start(make_volunteer, make_position):
    position, holder, (first, _) = full_with_waitlist(
        make_volunteer, make_position, starts_in_hours=10
    )
    services.cancel(holder)
    assert refresh(first).offer_expires_at == position.starts_at


def test_inside_two_hours_registers_directly(make_volunteer, make_position):
    _, holder, (first, _) = full_with_waitlist(make_volunteer, make_position, starts_in_hours=1)
    services.cancel(holder)
    assert refresh(first).status == "registered"


def test_skips_party_that_does_not_fit(make_volunteer, make_position):
    site_settings = SiteSettings.load()
    site_settings.max_guests = 2
    site_settings.save()
    position = make_position(slots=2)
    holder = services.register(make_volunteer(1), position)
    services.register(make_volunteer(4), position)
    big = services.register(make_volunteer(2), position, guests=[GuestData("A", "B")])
    small = services.register(make_volunteer(3), position)

    services.cancel(holder)

    assert refresh(big).status == "waitlisted"
    assert refresh(small).status == "offered"


def test_skips_volunteer_who_now_overlaps(make_volunteer, make_position):
    position, holder, (first, second) = full_with_waitlist(
        make_volunteer, make_position, starts_in_hours=48
    )
    # Staff moved another shift so it now overlaps the first waiter's waitlist place.
    other = make_position(starts_in_hours=100)
    services.register(first.volunteer, other)
    other.starts_at = position.starts_at
    other.ends_at = position.ends_at
    other.save()

    services.cancel(holder)

    assert refresh(first).status == "waitlisted"
    assert refresh(second).status == "offered"


def test_accept_offer(make_volunteer, make_position):
    _, holder, (first, _) = full_with_waitlist(make_volunteer, make_position)
    services.cancel(holder)
    services.accept_offer(refresh(first))
    assert refresh(first).status == "registered"


def test_decline_offer_moves_on(make_volunteer, make_position):
    _, holder, (first, second) = full_with_waitlist(make_volunteer, make_position)
    services.cancel(holder)
    services.decline_offer(refresh(first))
    assert refresh(first).status == "cancelled"
    assert refresh(second).status == "offered"


def test_accept_expired_offer_refused(make_volunteer, make_position):
    _, holder, (first, _) = full_with_waitlist(make_volunteer, make_position)
    services.cancel(holder)
    Registration.objects.filter(pk=first.pk).update(
        offer_expires_at=timezone.now() - timedelta(minutes=1)
    )
    with pytest.raises(RegistrationError, match="expired"):
        services.accept_offer(refresh(first))


def test_accept_refused_when_event_cancelled(make_volunteer, make_position):
    position, holder, (first, _) = full_with_waitlist(make_volunteer, make_position)
    services.cancel(holder)
    position.event.cancel()
    with pytest.raises(RegistrationError, match="isn't open"):
        services.accept_offer(refresh(first))


def test_expire_offers_moves_spots_on(make_volunteer, make_position):
    _, holder, (first, second) = full_with_waitlist(make_volunteer, make_position)
    services.cancel(holder)
    Registration.objects.filter(pk=first.pk).update(
        offer_expires_at=timezone.now() - timedelta(minutes=1)
    )

    assert services.expire_offers() == 1

    assert refresh(first).status == "expired"
    assert refresh(first).ended_at is not None
    assert refresh(second).status == "offered"


def test_expired_offers_are_marked_even_when_event_cancelled(make_volunteer, make_position):
    position, holder, (first, second) = full_with_waitlist(make_volunteer, make_position)
    services.cancel(holder)
    position.event.cancel()
    Registration.objects.filter(pk=first.pk).update(
        offer_expires_at=timezone.now() - timedelta(minutes=1)
    )
    services.expire_offers()
    assert refresh(first).status == "expired"
    assert refresh(second).status == "waitlisted"


def test_no_offers_while_event_cancelled(make_volunteer, make_position):
    position, holder, (first, _) = full_with_waitlist(make_volunteer, make_position)
    position.event.cancel()
    services.remove(holder)
    assert refresh(first).status == "waitlisted"


def test_remove_and_promote(make_volunteer, make_position):
    position, holder, (first, second) = full_with_waitlist(make_volunteer, make_position)
    services.remove(holder)
    assert refresh(holder).status == "removed"
    # first now holds an offer; staff promote second directly after raising spots
    position.slots = 2
    position.save()
    services.promote(refresh(second))
    assert refresh(second).status == "registered"


def test_promote_refused_when_party_does_not_fit(make_volunteer, make_position):
    _, _, (first, _) = full_with_waitlist(make_volunteer, make_position)
    with pytest.raises(RegistrationError, match="doesn't fit"):
        services.promote(first)


def test_promote_only_waitlisted(make_volunteer, make_position):
    _, holder, _ = full_with_waitlist(make_volunteer, make_position)
    with pytest.raises(RegistrationError, match="not on the waitlist"):
        services.promote(holder)


def test_cancellation_cutoff(volunteer, make_position):
    site_settings = SiteSettings.load()
    site_settings.cancellation_closes_hours_before = 72
    site_settings.save()
    registration = services.register(volunteer, make_position(starts_in_hours=48))
    with pytest.raises(RegistrationError, match="Cancellation has closed"):
        services.cancel(registration)
    services.remove(registration)  # staff are not bound by the cutoff
    assert refresh(registration).status == "removed"


def test_shrinking_party_offers_spot(make_volunteer, make_position):
    site_settings = SiteSettings.load()
    site_settings.max_guests = 1
    site_settings.save()
    position = make_position(slots=2)
    holder = services.register(make_volunteer(1), position, guests=[GuestData("A", "B")])
    waiter = services.register(make_volunteer(2), position)
    services.update(holder, [], "")
    assert refresh(waiter).status == "offered"


def test_beat_schedule_runs_expire_offers():
    entry = settings.CELERY_BEAT_SCHEDULE["expire-waitlist-offers"]
    assert entry["task"] == "registrations.tasks.expire_offers"
    assert entry["schedule"] == 300


def test_task_calls_service(make_volunteer, make_position):
    from registrations.tasks import expire_offers

    _, holder, (first, second) = full_with_waitlist(make_volunteer, make_position)
    services.cancel(holder)
    Registration.objects.filter(pk=first.pk).update(
        offer_expires_at=timezone.now() - timedelta(minutes=1)
    )
    expire_offers.delay()
    assert refresh(second).status == "offered"
