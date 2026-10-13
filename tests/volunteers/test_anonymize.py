from datetime import timedelta

import pytest
from allauth.account.models import EmailAddress
from django.core.files.storage import default_storage
from django.urls import reverse

from accounts.models import Profile
from notifications.models import OutgoingEmail
from registrations import services as registration_services
from registrations.models import Guest, Registration
from volunteers.services import VolunteerAdminError, anonymize, hours_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def history(volunteer, make_position, make_image_file):
    profile = volunteer.profile
    profile.photo = make_image_file()
    profile.date_of_birth = "1990-01-01"
    profile.address_line1 = "1 Main St"
    profile.save()
    EmailAddress.objects.create(user=volunteer, email=volunteer.email, verified=True, primary=True)
    past = Registration.objects.create(
        volunteer=volunteer,
        position=make_position(starts_in_hours=-48, hours=3),
        status="registered",
        attendance="attended",
        comments="I have a dog",
    )
    Guest.objects.create(registration=past, first_name="Sam", last_name="Lee", relationship="Son")
    OutgoingEmail.objects.create(
        to=volunteer.email,
        user=volunteer,
        kind="registered",
        subject="Hi Ada",
        text_body="Hi Ada",
        html_body="Hi Ada",
    )
    return past


def test_erases_personal_data_and_keeps_history(volunteer, history):
    photo = volunteer.profile.photo.name
    anonymize(volunteer, actor=None)

    volunteer.refresh_from_db()
    profile = Profile.objects.get(user=volunteer)
    assert volunteer.email == f"deleted-{volunteer.pk}@invalid"
    assert volunteer.is_active is False and not volunteer.has_usable_password()
    assert profile.first_name == profile.last_name == profile.phone == profile.address_line1 == ""
    assert profile.date_of_birth is None and not profile.photo
    assert profile.deleted_at is not None
    assert not EmailAddress.objects.filter(user=volunteer).exists()
    history.refresh_from_db()
    assert history.status == "registered" and history.attendance == "attended"
    assert history.comments == ""
    assert history.guests.get().first_name == "Guest"
    assert hours_for(volunteer) == timedelta(hours=3)
    email = OutgoingEmail.objects.get(user=volunteer)
    assert email.to == volunteer.email and email.text_body == ""
    assert photo  # deletion happens after commit (see next test)


def test_photo_deleted_after_commit(volunteer, history, django_capture_on_commit_callbacks):
    photo = volunteer.profile.photo.name
    with django_capture_on_commit_callbacks(execute=True):
        anonymize(volunteer)
    assert not default_storage.exists(photo)


def test_upcoming_registrations_removed_and_waitlist_moves(make_volunteer, make_position):
    position = make_position(slots=1)
    leaving = make_volunteer(1)
    registration_services.register(leaving, position)
    waiter = registration_services.register(make_volunteer(2), position)

    anonymize(leaving)

    waiter.refresh_from_db()
    assert waiter.status == "offered"
    assert Registration.objects.get(volunteer=leaving).status == "removed"
    assert OutgoingEmail.objects.filter(user=leaving, kind="removed").get().status == "suppressed"


def test_cannot_log_in_afterwards(client, volunteer):
    anonymize(volunteer)
    assert (
        client.login(username=volunteer.username, password="correct-horse-battery-staple-42")
        is False
    )


def test_refusals(volunteer, org_admin, django_user_model):
    root = django_user_model.objects.create_superuser(
        username="root", email="root@example.org", password="x"
    )
    with pytest.raises(VolunteerAdminError, match="Superuser"):
        anonymize(root, actor=org_admin)
    with pytest.raises(VolunteerAdminError, match="your own account"):
        anonymize(org_admin, actor=org_admin)
    with pytest.raises(VolunteerAdminError, match="another Admin"):
        anonymize(org_admin)


def test_admin_deletes_from_volunteer_page(client, org_admin, volunteer):
    client.force_login(org_admin)
    assert client.get(reverse("manage_volunteer_delete", args=[volunteer.pk])).status_code == 200
    response = client.post(reverse("manage_volunteer_delete", args=[volunteer.pk]), follow=True)
    assert "Account deleted" in response.content.decode()
    assert Profile.objects.get(user=volunteer).deleted_at is not None


def test_coordinator_cannot_delete(client, coordinator, volunteer):
    client.force_login(coordinator)
    assert client.post(reverse("manage_volunteer_delete", args=[volunteer.pk])).status_code == 403


def test_self_delete_requires_typed_email(client, volunteer):
    client.force_login(volunteer)
    response = client.post(reverse("account_delete"), {"email": "wrong@example.org"})
    assert response.status_code == 200
    assert Profile.objects.get(user=volunteer).deleted_at is None

    response = client.post(
        reverse("account_delete"), {"email": volunteer.email.upper()}, follow=True
    )
    assert "Your account has been deleted" in response.content.decode()
    assert Profile.objects.get(user=volunteer).deleted_at is not None
    assert "_auth_user_id" not in client.session


def test_admin_cannot_self_delete(client, org_admin):
    client.force_login(org_admin)
    response = client.post(reverse("account_delete"), {"email": org_admin.email}, follow=True)
    assert "another Admin" in response.content.decode()
    assert Profile.objects.get(user=org_admin).deleted_at is None


def test_roster_shows_deleted_volunteer(client, coordinator, volunteer, history):
    anonymize(volunteer)
    client.force_login(coordinator)
    content = client.get(reverse("manage_roster", args=[history.position_id])).content.decode()
    assert "Deleted volunteer" in content
    assert "@invalid" not in content
