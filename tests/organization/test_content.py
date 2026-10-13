import pytest
from django.core.files.storage import default_storage
from django.urls import reverse

from core.images import variant_name
from organization.models import SiteSettings

pytestmark = pytest.mark.django_db


def set_content(**values):
    site_settings = SiteSettings.load()
    for name, value in values.items():
        setattr(site_settings, name, value)
    site_settings.save()


def test_home_defaults(client):
    content = client.get(reverse("home")).content.decode()
    assert "<h1" in content and SiteSettings.load().org_name in content
    assert "About us" not in content  # hidden while about_body is empty


def test_home_slots(client):
    set_content(
        home_headline="Feed your neighbors",
        home_intro="<div>Join <strong>us</strong></div><script>x()</script>",
        about_title="Who we are",
        about_body="<div>Since 1999</div>",
        footer_note="Questions? Call 617-555-0100",
    )
    content = client.get(reverse("home")).content.decode()
    assert "Feed your neighbors" in content
    assert "<strong>us</strong>" in content and "<script>x()" not in content
    assert "Who we are" in content and "Since 1999" in content
    assert "Questions? Call 617-555-0100" in content


def test_footer_note_alone_shows_footer(client):
    set_content(footer_note="Thanks for volunteering")
    assert "Thanks for volunteering" in client.get(reverse("events")).content.decode()


def test_settings_page_sections_and_images(
    client, org_admin, make_image_file, django_capture_on_commit_callbacks
):
    from tests.organization.test_settings_page import VALID

    client.force_login(org_admin)
    page = client.get("/manage/settings/").content.decode()
    for heading in ("Organization", "Home page", "Volunteer profiles", "Registration", "Reminders"):
        assert heading in page
    assert "trix-editor" in page
    with django_capture_on_commit_callbacks(execute=True):
        client.post(
            "/manage/settings/",
            {
                **VALID,
                "home_headline": "Hello",
                "home_image": make_image_file(name="hero.png", size=(2000, 800)),
                "about_image": make_image_file(name="about.png"),
            },
        )
    site_settings = SiteSettings.load()
    assert site_settings.home_headline == "Hello"
    assert default_storage.exists(variant_name(site_settings.home_image.name, 1600))
    assert default_storage.exists(variant_name(site_settings.about_image.name, 800))


def test_cached_settings_keep_images():
    set_content(home_image="site/hero.png", about_image="site/about.png")
    SiteSettings.load()  # fills the cache
    cached = SiteSettings.load()
    assert cached.home_image.name == "site/hero.png"
    assert cached.about_image.name == "site/about.png"
