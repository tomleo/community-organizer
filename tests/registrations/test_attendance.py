import pytest
from django.urls import reverse

from registrations import services
from registrations.models import Registration
from registrations.services import RegistrationError

pytestmark = pytest.mark.django_db


def started(volunteer, make_position, status="registered"):
    return Registration.objects.create(
        volunteer=volunteer, position=make_position(starts_in_hours=-1, hours=3), status=status
    )


def test_mark_and_clear(volunteer, coordinator, make_position):
    registration = started(volunteer, make_position)
    services.mark_attendance(registration, "attended", by=coordinator)
    registration.refresh_from_db()
    assert registration.attendance == "attended"
    assert registration.attendance_marked_by == coordinator
    services.mark_attendance(registration, "", by=coordinator)
    registration.refresh_from_db()
    assert registration.attendance == "" and registration.attendance_marked_at is None


def test_refused_before_start_or_for_waitlisted(
    volunteer, coordinator, make_position, make_volunteer
):
    future = Registration.objects.create(
        volunteer=volunteer, position=make_position(), status="registered"
    )
    with pytest.raises(RegistrationError, match="once the shift has started"):
        services.mark_attendance(future, "attended", by=coordinator)
    waiting = started(make_volunteer(2), make_position, status="waitlisted")
    with pytest.raises(RegistrationError, match="Only registered"):
        services.mark_attendance(waiting, "no_show", by=coordinator)


def test_mark_all_unmarked(coordinator, make_volunteer, make_position):
    position = make_position(starts_in_hours=-1, slots=5)
    first = Registration.objects.create(
        volunteer=make_volunteer(1), position=position, status="registered"
    )
    second = Registration.objects.create(
        volunteer=make_volunteer(2), position=position, status="registered", attendance="no_show"
    )
    assert services.mark_all_attended(position, by=coordinator) == 1
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.attendance == "attended" and second.attendance == "no_show"


def test_roster_buttons_toggle(client, coordinator, volunteer, make_position):
    registration = started(volunteer, make_position)
    client.force_login(coordinator)
    url = reverse("manage_attendance", args=[registration.pk])
    content = client.get(reverse("manage_roster", args=[registration.position_id])).content.decode()
    assert url in content
    client.post(url, {"attendance": "attended"})
    registration.refresh_from_db()
    assert registration.attendance == "attended"
    client.post(url, {"attendance": "attended"})  # pressing again clears
    registration.refresh_from_db()
    assert registration.attendance == ""


def test_roster_has_no_buttons_before_start(client, coordinator, volunteer, make_position):
    registration = Registration.objects.create(
        volunteer=volunteer, position=make_position(), status="registered"
    )
    client.force_login(coordinator)
    content = client.get(reverse("manage_roster", args=[registration.position_id])).content.decode()
    assert reverse("manage_attendance", args=[registration.pk]) not in content


def test_mark_all_view_and_permissions(
    client, coordinator, volunteer, make_position, make_volunteer
):
    registration = started(volunteer, make_position)
    client.force_login(make_volunteer(2))
    assert (
        client.post(
            reverse("manage_mark_all_attended", args=[registration.position_id])
        ).status_code
        == 403
    )
    client.force_login(coordinator)
    client.post(reverse("manage_mark_all_attended", args=[registration.position_id]))
    registration.refresh_from_db()
    assert registration.attendance == "attended"


def test_profile_shows_hours(client, volunteer, make_position):
    Registration.objects.create(
        volunteer=volunteer,
        position=make_position(starts_in_hours=-48, hours=3),
        status="registered",
        attendance="attended",
    )
    client.force_login(volunteer)
    assert "3 hours · 1 shift attended" in client.get(reverse("profile")).content.decode()


def test_announcement_toggle_on_profile_form(client, volunteer):
    client.force_login(volunteer)
    assert 'name="announcement_emails"' in client.get(reverse("profile_edit")).content.decode()
