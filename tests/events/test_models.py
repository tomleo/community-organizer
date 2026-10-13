from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.utils import timezone

from events.models import Event, EventStateError, Location, Position

pytestmark = pytest.mark.django_db


def test_new_event_is_draft(location):
    event = Event.objects.create(title="Cleanup", location=location)
    assert event.status == Event.Status.DRAFT
    assert event.is_public is False


def test_publish_requires_a_position(make_event):
    event = make_event(status="draft", positions=())
    with pytest.raises(EventStateError, match="Add a position"):
        event.publish()
    event.refresh_from_db()
    assert event.status == Event.Status.DRAFT


def test_publish_cancel_reinstate(make_event):
    event = make_event(status="draft")
    event.publish()
    assert event.status == Event.Status.PUBLISHED
    event.cancel()
    assert Event.objects.get(pk=event.pk).status == Event.Status.CANCELLED
    event.reinstate()
    assert Event.objects.get(pk=event.pk).status == Event.Status.PUBLISHED


@pytest.mark.parametrize(
    ("status", "method"),
    [
        ("published", "publish"),
        ("cancelled", "publish"),
        ("draft", "cancel"),
        ("cancelled", "cancel"),
        ("draft", "reinstate"),
        ("published", "reinstate"),
    ],
)
def test_invalid_transitions(make_event, status, method):
    event = make_event(status=status)
    with pytest.raises(EventStateError):
        getattr(event, method)()
    assert Event.objects.get(pk=event.pk).status == status


def test_archive_and_restore(make_event):
    event = make_event()
    event.archive()
    assert Event.objects.get(pk=event.pk).archived_at is not None
    assert event.is_public is False
    event.restore()
    assert Event.objects.get(pk=event.pk).archived_at is None
    assert event.is_public is True


def test_pin_and_unpin(make_event):
    event = make_event()
    event.pin()
    assert Event.objects.get(pk=event.pk).pinned is True
    event.unpin()
    assert Event.objects.get(pk=event.pk).pinned is False


def test_description_is_sanitized_on_save(location):
    event = Event.objects.create(
        title="x", location=location, description="<div>ok</div><script>bad()</script>"
    )
    assert Event.objects.get(pk=event.pk).description == "<div>ok</div>"


def test_position_must_end_after_start(make_event):
    event = make_event(positions=())
    start = timezone.now()
    position = Position(event=event, title="x", starts_at=start, ends_at=start, slots=1)
    with pytest.raises(ValidationError) as excinfo:
        position.full_clean()
    assert "ends_at" in excinfo.value.message_dict
    with pytest.raises(IntegrityError):
        position.save()


def test_position_effective_location(make_event, location):
    other = Location.objects.create(
        name="Park",
        address_line1="1 Park Rd",
        city="Boston",
        region="MA",
        postal_code="02119",
        country="USA",
    )
    event = make_event()
    position = event.positions.get()
    assert position.effective_location == location
    position.location = other
    assert position.effective_location == other


def test_position_can_delete_only_on_drafts(make_event):
    assert make_event(status="draft").positions.get().can_delete is True
    assert make_event(status="published").positions.get().can_delete is False


def test_location_requires_both_coordinates(location):
    location.latitude = Decimal("42.35")
    with pytest.raises(ValidationError):
        location.full_clean()
    location.longitude = Decimal("-71.06")
    location.full_clean()


def test_location_coordinate_ranges(location):
    location.latitude, location.longitude = Decimal("91"), Decimal("0")
    with pytest.raises(ValidationError) as excinfo:
        location.full_clean()
    assert "latitude" in excinfo.value.message_dict


def test_location_in_use_is_protected(make_event, location):
    make_event()
    with pytest.raises(ProtectedError):
        location.delete()


def test_events_using_includes_position_overrides(make_event, location):
    venue = Location.objects.create(
        name="Gym",
        address_line1="2 School St",
        city="Boston",
        region="MA",
        postal_code="02120",
        country="USA",
    )
    event = make_event()
    Position.objects.filter(event=event).update(location=venue)
    assert list(venue.events_using()) == [event]
    with pytest.raises(ProtectedError):
        venue.delete()


@pytest.mark.parametrize("group_name", ["Coordinator", "Admin"])
def test_role_groups_get_events_permissions(group_name):
    codenames = set(
        Group.objects.get(name=group_name).permissions.values_list("codename", flat=True)
    )
    for model in ("location", "event", "position", "eventphoto"):
        for action in ("add", "change", "delete"):
            assert f"{action}_{model}" in codenames


def test_positions_ordered_by_start(make_event):
    event = make_event(positions=((48, 1), (24, 1)))
    starts = list(event.positions.values_list("starts_at", flat=True))
    assert starts == sorted(starts)
    assert starts[0] < starts[1] - timedelta(hours=1)
