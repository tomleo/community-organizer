import pytest
from django.core.files.storage import default_storage
from django.urls import reverse

from core.images import variant_name
from organization.models import SiteSettings
from organization.roles import Role, set_role

pytestmark = pytest.mark.django_db

URL = "/manage/settings/"
VALID = {
    "org_name": "Neighborhood Pantry",
    "contact_email": "hello@pantry.example",
    "website_url": "https://pantry.example",
    "time_zone": "America/New_York",
    "require_name": "on",
    "require_phone": "on",
    "max_guests": "0",
    "offer_window_hours": "24",
    "registration_closes_hours_before": "0",
    "cancellation_closes_hours_before": "0",
    "reminder_hours_before": "24",
    "about_title": "About us",
}


def test_url_name():
    assert reverse("manage_settings") == URL


def test_anonymous_redirected_to_login(client):
    response = client.get(URL)
    assert response.status_code == 302
    assert response.url.startswith(reverse("account_login"))


@pytest.mark.parametrize("role", [Role.VOLUNTEER, Role.COORDINATOR])
def test_non_admins_forbidden(client, complete_user, role):
    user = complete_user()
    set_role(user, role)
    client.force_login(user)
    assert client.get(URL).status_code == 403


def test_admin_updates_settings(client, complete_user):
    user = complete_user()
    set_role(user, Role.ADMIN)
    client.force_login(user)

    response = client.post(URL, VALID)

    assert response.status_code == 302
    site_settings = SiteSettings.load()
    assert site_settings.org_name == "Neighborhood Pantry"
    assert site_settings.time_zone == "America/New_York"
    assert site_settings.require_date_of_birth is False


def test_superuser_can_open_page(client, django_user_model):
    superuser = django_user_model.objects.create_superuser(
        username="root", email="root@example.org", password="x"
    )
    superuser.profile.first_name, superuser.profile.last_name = "Root", "User"
    superuser.profile.phone = "617-555-0100"
    superuser.profile.save()
    client.force_login(superuser)
    assert client.get(URL).status_code == 200


def test_invalid_time_zone_rejected(client, complete_user):
    user = complete_user()
    set_role(user, Role.ADMIN)
    client.force_login(user)

    response = client.post(URL, {**VALID, "time_zone": "Mars/Olympus_Mons"})

    assert response.status_code == 200
    assert "time_zone" in response.context["form"].errors


def test_logo_upload_creates_variants(
    client, complete_user, make_image_file, django_capture_on_commit_callbacks
):
    user = complete_user()
    set_role(user, Role.ADMIN)
    client.force_login(user)

    with django_capture_on_commit_callbacks(execute=True):
        client.post(URL, {**VALID, "logo": make_image_file(name="logo.png")})

    assert default_storage.exists(variant_name(SiteSettings.load().logo.name, 128))


def test_manage_link_only_for_managers(client, complete_user):
    volunteer = complete_user("volunteer@example.org")
    admin = complete_user("admin@example.org")
    set_role(admin, Role.ADMIN)

    client.force_login(volunteer)
    assert URL not in client.get(reverse("home")).content.decode()
    client.force_login(admin)
    assert URL in client.get(reverse("home")).content.decode()
