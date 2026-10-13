import pytest
from django.core.files.storage import default_storage
from django.urls import reverse

from accounts.models import Profile
from core.images import variant_name
from organization.models import SiteSettings

pytestmark = pytest.mark.django_db

VALID = {"first_name": "Grace", "last_name": "Hopper", "phone": "617-555-0199"}


def test_profile_requires_login(client):
    response = client.get(reverse("profile"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("account_login"))


def test_profile_shows_details(client, complete_user):
    client.force_login(complete_user())
    content = client.get(reverse("profile")).content.decode()
    assert "Ada Lovelace" in content
    assert "617-555-0100" in content


def test_edit_saves_profile(client, complete_user):
    user = complete_user()
    client.force_login(user)

    response = client.post(reverse("profile_edit"), VALID)

    assert response.status_code == 302
    assert response.url == reverse("profile")
    assert Profile.objects.get(user=user).first_name == "Grace"


def test_edit_enforces_required_fields(client, complete_user):
    client.force_login(complete_user())

    response = client.post(reverse("profile_edit"), {**VALID, "first_name": ""})

    assert response.status_code == 200
    assert "first_name" in response.context["form"].errors


def test_fields_optional_when_settings_say_so(client, complete_user):
    site_settings = SiteSettings.load()
    site_settings.require_name = False
    site_settings.require_phone = False
    site_settings.save()
    client.force_login(complete_user())

    response = client.post(reverse("profile_edit"), {})

    assert response.status_code == 302


def test_photo_upload_creates_variants(
    client, complete_user, make_image_file, django_capture_on_commit_callbacks
):
    user = complete_user()
    client.force_login(user)

    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("profile_edit"), {**VALID, "photo": make_image_file()})

    photo_name = Profile.objects.get(user=user).photo.name
    assert default_storage.exists(variant_name(photo_name, 512))
    assert default_storage.exists(variant_name(photo_name, 128))


def test_photo_must_be_an_image(client, complete_user):
    from django.core.files.uploadedfile import SimpleUploadedFile

    client.force_login(complete_user())
    fake = SimpleUploadedFile("photo.jpg", b"not an image", content_type="image/jpeg")

    response = client.post(reverse("profile_edit"), {**VALID, "photo": fake})

    assert response.status_code == 200
    assert "photo" in response.context["form"].errors


def test_edit_works_when_stored_photo_file_is_missing(client, complete_user):
    # e.g. a database restored without its media directory
    user = complete_user()
    Profile.objects.filter(user=user).update(photo="profiles/gone.png")
    client.force_login(user)

    response = client.post(reverse("profile_edit"), VALID)

    assert response.status_code == 302
    assert Profile.objects.get(user=user).first_name == "Grace"
