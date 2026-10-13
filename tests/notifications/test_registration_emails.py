from datetime import timedelta

import pytest
from django.utils import timezone

from notifications.models import OutgoingEmail
from registrations import services
from registrations.models import Registration

pytestmark = pytest.mark.django_db


def kinds_for(user):
    return list(
        OutgoingEmail.objects.filter(user=user).order_by("pk").values_list("kind", flat=True)
    )


def test_register_and_waitlist(make_volunteer, make_position):
    position = make_position(slots=1)
    first, second = make_volunteer(1), make_volunteer(2)
    services.register(first, position)
    services.register(second, position)
    assert kinds_for(first) == ["registered"]
    assert kinds_for(second) == ["waitlisted"]
    assert "#1" in OutgoingEmail.objects.get(user=second).text_body


def test_cancel_offer_accept(make_volunteer, make_position):
    position = make_position(slots=1)
    holder = services.register(make_volunteer(1), position)
    waiter = services.register(make_volunteer(2), position)
    services.cancel(holder)
    waiter.refresh_from_db()
    services.accept_offer(waiter)
    assert kinds_for(holder.volunteer) == ["registered", "cancelled"]
    assert kinds_for(waiter.volunteer) == ["waitlisted", "offered", "registered"]


def test_decline_and_leaving_waitlist_send_nothing(make_volunteer, make_position):
    position = make_position(slots=1)
    holder = services.register(make_volunteer(1), position)
    waiter = services.register(make_volunteer(2), position)
    leaver = services.register(make_volunteer(3), position)
    services.cancel(leaver)
    services.cancel(holder)
    waiter.refresh_from_db()
    services.decline_offer(waiter)
    assert kinds_for(leaver.volunteer) == ["waitlisted"]
    assert kinds_for(waiter.volunteer) == ["waitlisted", "offered"]


def test_auto_registered_inside_two_hours(make_volunteer, make_position):
    position = make_position(slots=1, starts_in_hours=1)
    holder = services.register(make_volunteer(1), position)
    waiter = services.register(make_volunteer(2), position)
    services.cancel(holder)
    assert kinds_for(waiter.volunteer) == ["waitlisted", "auto_registered"]


def test_offer_expired(make_volunteer, make_position):
    position = make_position(slots=1)
    holder = services.register(make_volunteer(1), position)
    waiter = services.register(make_volunteer(2), position)
    services.cancel(holder)
    Registration.objects.filter(pk=waiter.pk).update(
        offer_expires_at=timezone.now() - timedelta(minutes=1)
    )
    services.expire_offers()
    assert kinds_for(waiter.volunteer) == ["waitlisted", "offered", "offer_expired"]


def test_remove_and_promote(make_volunteer, make_position):
    position = make_position(slots=1)
    holder = services.register(make_volunteer(1), position)
    waiter = services.register(make_volunteer(2), position)
    position.slots = 2
    position.save()
    services.promote(waiter)
    services.remove(holder)
    assert kinds_for(waiter.volunteer) == ["waitlisted", "registered"]
    assert kinds_for(holder.volunteer) == ["registered", "removed"]
    assert "METHOD:CANCEL" in OutgoingEmail.objects.get(kind="removed").ics


def test_removing_waitlisted_has_no_calendar(make_volunteer, make_position):
    position = make_position(slots=1)
    services.register(make_volunteer(1), position)
    waiter = services.register(make_volunteer(2), position)
    services.remove(waiter)
    assert OutgoingEmail.objects.get(kind="removed").ics == ""


def test_refused_registration_queues_nothing(volunteer, make_position):
    position = make_position()
    services.register(volunteer, position)
    with pytest.raises(services.RegistrationError):
        services.register(volunteer, position)
    assert kinds_for(volunteer) == ["registered"]


def test_editing_guests_sends_nothing(volunteer, make_position):
    registration = services.register(volunteer, make_position())
    services.update(registration, [], "New comment")
    assert kinds_for(volunteer) == ["registered"]
