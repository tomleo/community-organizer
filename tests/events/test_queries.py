import pytest
from django.utils import timezone

from events.models import Event, EventPhoto
from events.querysets import STAFF_TABS

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("status", "archived", "public"),
    [
        ("draft", False, False),
        ("published", False, True),
        ("cancelled", False, True),
        ("draft", True, False),
        ("published", True, False),
        ("cancelled", True, False),
    ],
)
def test_public_visibility(make_event, status, archived, public):
    event = make_event(status=status)
    if archived:
        event.archive()
    assert Event.objects.public().filter(pk=event.pk).exists() is public


def test_with_dates_annotations(make_event):
    event = make_event(positions=((24, 2), (48, 3)))
    dated = Event.objects.with_dates().get(pk=event.pk)
    positions = list(event.positions.all())
    assert dated.starts_at == positions[0].starts_at
    assert dated.ends_at == positions[1].ends_at
    assert dated.position_count == 2
    assert dated.total_slots == 10


def test_with_dates_without_positions(make_event):
    dated = Event.objects.with_dates().get(pk=make_event(status="draft", positions=()).pk)
    assert dated.starts_at is None
    assert dated.ends_at is None
    assert dated.position_count == 0


def test_with_dates_is_idempotent(make_event):
    make_event()
    assert Event.objects.with_dates().with_dates().upcoming().count() == 1


def test_upcoming_and_past_boundary(make_event):
    ongoing = make_event(title="ongoing", positions=((-1, 2),))
    just_ended = make_event(title="ended", positions=((-2, 1),))
    later = make_event(title="later", positions=((48, 1),))
    soon = make_event(title="soon", positions=((2, 1),))

    assert list(Event.objects.upcoming()) == [ongoing, soon, later]
    assert list(Event.objects.past()) == [just_ended]


def test_upcoming_uses_last_position_end(make_event):
    event = make_event(positions=((-30, 1), (5, 1)))
    assert Event.objects.upcoming().filter(pk=event.pk).exists()


def test_featured_prefers_pinned(make_event):
    make_event(title="a", positions=((24, 1),))
    pinned = make_event(title="b", positions=((48, 1),))
    pinned.pin()
    assert list(Event.objects.featured()) == [pinned]


def test_featured_falls_back_to_next_three(make_event):
    events = [make_event(title=str(hours), positions=((hours, 1),)) for hours in (10, 20, 30, 40)]
    make_event(title="draft", status="draft", positions=((5, 1),))
    assert list(Event.objects.featured()) == events[:3]


def test_featured_ignores_past_pinned(make_event):
    old = make_event(positions=((-48, 1),))
    old.pin()
    upcoming = make_event(positions=((24, 1),))
    assert list(Event.objects.featured()) == [upcoming]


def test_with_cover_prefetches_photos(make_event, make_image_file, django_assert_num_queries):
    for index in range(3):
        event = make_event(title=f"e{index}")
        EventPhoto.objects.create(event=event, image=make_image_file(), position=0)
    with django_assert_num_queries(2):
        events = list(Event.objects.public().upcoming().with_cover())
        covers = [event.photos.all()[0] for event in events]
    assert len(covers) == 3


def test_staff_tabs(make_event):
    now = timezone.now()
    make_event(title="empty draft", status="draft", positions=())
    make_event(title="upcoming", positions=((24, 1),))
    make_event(title="past", positions=((-48, 1),))
    make_event(title="cancelled", status="cancelled", positions=((24, 1),))
    archived = make_event(title="archived", positions=((24, 1),))
    archived.archive()

    def titles(tab):
        return [event.title for event in Event.objects.for_staff(tab, now=now)]

    assert titles("upcoming") == ["empty draft", "upcoming", "cancelled"]
    assert titles("past") == ["past"]
    assert titles("drafts") == ["empty draft"]
    assert titles("cancelled") == ["cancelled"]
    assert titles("archived") == ["archived"]
    assert set(STAFF_TABS) == {"upcoming", "past", "drafts", "cancelled", "archived"}


def test_staff_unknown_tab_falls_back_to_upcoming(make_event):
    make_event(title="x", positions=((24, 1),))
    assert [e.title for e in Event.objects.for_staff("nonsense")] == ["x"]
