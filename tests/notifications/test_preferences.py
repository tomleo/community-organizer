import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

VALID = {"first_name": "Ada", "last_name": "Lovelace", "phone": "617-555-0100"}


def test_volunteer_sees_reminder_toggle_only(client, volunteer):
    client.force_login(volunteer)
    content = client.get(reverse("profile_edit")).content.decode()
    assert 'name="reminder_emails"' in content
    assert 'name="staff_digest"' not in content


def test_staff_sees_digest_toggle(client, coordinator):
    client.force_login(coordinator)
    assert 'name="staff_digest"' in client.get(reverse("profile_edit")).content.decode()


def test_turn_reminders_off(client, volunteer):
    client.force_login(volunteer)
    client.post(reverse("profile_edit"), VALID)  # unchecked checkbox = False
    volunteer.profile.refresh_from_db()
    assert volunteer.profile.reminder_emails is False


def test_staff_opt_into_digest(client, coordinator):
    client.force_login(coordinator)
    client.post(reverse("profile_edit"), {**VALID, "reminder_emails": "on", "staff_digest": "on"})
    coordinator.profile.refresh_from_db()
    assert coordinator.profile.staff_digest is True


def test_volunteer_cannot_set_digest(client, volunteer):
    client.force_login(volunteer)
    client.post(reverse("profile_edit"), {**VALID, "staff_digest": "on"})
    volunteer.profile.refresh_from_db()
    assert volunteer.profile.staff_digest is False
