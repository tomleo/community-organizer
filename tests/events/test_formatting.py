from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from events.templatetags.event_tags import date_range, time_range

NY = ZoneInfo("America/New_York")


def ny(*args):
    return datetime(*args, tzinfo=NY)


@pytest.fixture(autouse=True)
def _new_york():
    with timezone.override(NY):
        yield


def test_same_day():
    assert date_range(ny(2026, 11, 7, 9, 0), ny(2026, 11, 7, 13, 0)) == (
        "Sat, Nov 7, 2026 · 9:00 AM – 1:00 PM"
    )


def test_multi_day_same_year():
    assert date_range(ny(2026, 11, 7, 9), ny(2026, 11, 8, 17)) == "Nov 7 – Nov 8, 2026"


def test_across_years():
    assert date_range(ny(2026, 12, 31, 20), ny(2027, 1, 1, 2)) == "Dec 31, 2026 – Jan 1, 2027"


def test_no_dates():
    assert date_range(None, None) == "Dates to be announced"


def test_uses_site_time_zone_not_utc():
    # 03:00 UTC on Nov 8 is still Nov 7 in New York.
    start = datetime(2026, 11, 8, 1, 0, tzinfo=ZoneInfo("UTC"))
    end = datetime(2026, 11, 8, 3, 0, tzinfo=ZoneInfo("UTC"))
    assert date_range(start, end) == "Sat, Nov 7, 2026 · 8:00 PM – 10:00 PM"


def test_time_range_same_day():
    assert time_range(ny(2026, 11, 7, 9, 30), ny(2026, 11, 7, 12, 0)) == "9:30 AM – 12:00 PM"


def test_time_range_overnight_shows_next_day():
    assert time_range(ny(2026, 11, 7, 22, 0), ny(2026, 11, 8, 2, 0)) == "10:00 PM – Sun 2:00 AM"
