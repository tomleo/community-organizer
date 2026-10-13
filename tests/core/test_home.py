import pytest
from django.urls import reverse

from organization.models import SiteSettings

pytestmark = pytest.mark.django_db


def test_home_shows_org_name(client):
    site_settings = SiteSettings.load()
    site_settings.org_name = "Neighborhood Pantry"
    site_settings.save()

    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert "Neighborhood Pantry" in response.content.decode()


def test_anonymous_navbar_offers_login_and_signup(client):
    content = client.get(reverse("home")).content.decode()
    assert reverse("account_login") in content
    assert reverse("account_signup") in content


def test_authenticated_navbar_offers_logout(client, complete_user):
    client.force_login(complete_user())
    content = client.get(reverse("home")).content.decode()
    assert reverse("account_logout") in content
    assert reverse("account_signup") not in content


def test_footer_shows_contact_details(client):
    site_settings = SiteSettings.load()
    site_settings.contact_email = "hello@pantry.example"
    site_settings.website_url = "https://pantry.example"
    site_settings.save()

    content = client.get(reverse("home")).content.decode()

    assert 'href="mailto:hello@pantry.example"' in content
    assert 'href="https://pantry.example"' in content


def test_login_page_uses_site_layout(client):
    content = client.get(reverse("account_login")).content.decode()
    assert 'class="navbar' in content
    assert "app-form" in content


def test_login_page_hides_google_without_credentials(client, settings):
    settings.SOCIALACCOUNT_PROVIDERS = {"google": {"SCOPE": ["profile", "email"]}}
    assert "/accounts/google/login/" not in client.get(reverse("account_login")).content.decode()


def test_login_page_shows_google_with_credentials(client, settings):
    settings.SOCIALACCOUNT_PROVIDERS = {
        "google": {"APP": {"client_id": "id", "secret": "secret", "key": ""}}
    }
    assert "/accounts/google/login/" in client.get(reverse("account_login")).content.decode()
