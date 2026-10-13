import pytest
from django.urls import reverse

from notifications.models import OutgoingEmail
from organization.roles import Role, get_role
from registrations.models import Registration
from volunteers.services import VolunteerAdminError, change_role

pytestmark = pytest.mark.django_db


def test_detail_shows_profile_stats_and_shifts(client, coordinator, volunteer, make_position):
    past = make_position(title="Old shift", starts_in_hours=-48, hours=3)
    Registration.objects.create(
        volunteer=volunteer, position=past, status="registered", attendance="attended"
    )
    Registration.objects.create(
        volunteer=volunteer, position=make_position(title="Next shift"), status="registered"
    )
    client.force_login(coordinator)
    content = client.get(reverse("manage_volunteer", args=[volunteer.pk])).content.decode()
    assert "617-555-0100" in content
    assert "Old shift" in content and "Attended" in content
    assert "Next shift" in content
    assert "3 hours" in content


def test_detail_permissions(client, volunteer, make_volunteer):
    client.force_login(make_volunteer(2))
    assert client.get(reverse("manage_volunteer", args=[volunteer.pk])).status_code == 403


def test_recent_emails_only_for_email_log_viewers(client, coordinator, org_admin, volunteer):
    OutgoingEmail.objects.create(
        to=volunteer.email,
        user=volunteer,
        kind="registered",
        subject="Hello there",
        text_body="t",
        html_body="h",
    )
    url = reverse("manage_volunteer", args=[volunteer.pk])
    client.force_login(coordinator)
    assert "Hello there" not in client.get(url).content.decode()
    client.force_login(org_admin)
    assert "Hello there" in client.get(url).content.decode()


def test_admin_changes_role(client, org_admin, volunteer):
    client.force_login(org_admin)
    response = client.post(
        reverse("manage_volunteer_role", args=[volunteer.pk]), {"role": "coordinator"}, follow=True
    )
    assert get_role(volunteer) == Role.COORDINATOR
    assert "Role changed" in response.content.decode()


def test_coordinator_cannot_change_roles(client, coordinator, volunteer):
    client.force_login(coordinator)
    assert (
        client.post(
            reverse("manage_volunteer_role", args=[volunteer.pk]), {"role": "admin"}
        ).status_code
        == 403
    )
    assert get_role(volunteer) == Role.VOLUNTEER


def test_role_selector_only_for_admins(client, coordinator, org_admin, volunteer):
    url = reverse("manage_volunteer", args=[volunteer.pk])
    client.force_login(coordinator)
    assert 'name="role"' not in client.get(url).content.decode()
    client.force_login(org_admin)
    assert 'name="role"' in client.get(url).content.decode()


def test_cannot_change_own_role(org_admin):
    with pytest.raises(VolunteerAdminError, match="your own role"):
        change_role(org_admin, org_admin, Role.VOLUNTEER)


def test_cannot_change_superuser_role(org_admin, django_user_model):
    root = django_user_model.objects.create_superuser(
        username="root", email="root@example.org", password="x"
    )
    with pytest.raises(VolunteerAdminError, match="Superuser"):
        change_role(org_admin, root, Role.VOLUNTEER)


def test_invalid_role_rejected(client, org_admin, volunteer):
    client.force_login(org_admin)
    assert (
        client.post(
            reverse("manage_volunteer_role", args=[volunteer.pk]), {"role": "owner"}
        ).status_code
        == 400
    )


def test_directory_links_to_volunteer_page(client, coordinator, volunteer):
    client.force_login(coordinator)
    content = client.get(reverse("manage_volunteers")).content.decode()
    assert reverse("manage_volunteer", args=[volunteer.pk]) in content
