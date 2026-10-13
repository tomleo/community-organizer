import pytest
from allauth.socialaccount.adapter import get_adapter as get_social_adapter
from django.test import RequestFactory
from django.urls import reverse

import accounts.adapters
from tests.constants import PASSWORD

pytestmark = pytest.mark.django_db


def _signup(client, email):
    return client.post(
        reverse("account_signup"),
        {"email": email, "password1": PASSWORD, "password2": PASSWORD},
    )


def test_signup_sends_verification_code(client, mailoutbox):
    response = _signup(client, "volunteer@example.org")

    assert response.status_code == 302
    assert response.url == reverse("account_email_verification_sent")
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["volunteer@example.org"]


def test_allauth_email_goes_through_queue(client, monkeypatch):
    queued = []
    monkeypatch.setattr(accounts.adapters, "queue_email", queued.append)

    _signup(client, "volunteer@example.org")

    assert len(queued) == 1
    assert queued[0].to == ["volunteer@example.org"]


def test_allauth_email_replies_to_contact_email(client, mailoutbox):
    from organization.models import SiteSettings

    site_settings = SiteSettings.load()
    site_settings.contact_email = "hello@pantry.example"
    site_settings.save()

    _signup(client, "volunteer@example.org")

    assert mailoutbox[0].reply_to == ["hello@pantry.example"]


def test_same_email_different_case_does_not_create_second_account(client, django_user_model):
    _signup(client, "volunteer@example.org")
    client.logout()
    _signup(client, "Volunteer@Example.org")

    assert django_user_model.objects.filter(email__iexact="volunteer@example.org").count() == 1


def test_google_not_offered_without_credentials(settings):
    settings.SOCIALACCOUNT_PROVIDERS = {"google": {"SCOPE": ["profile", "email"]}}
    providers = get_social_adapter().list_providers(RequestFactory().get("/"))
    assert [provider.id for provider in providers] == []


def test_google_offered_with_credentials(settings):
    settings.SOCIALACCOUNT_PROVIDERS = {
        "google": {"APP": {"client_id": "id", "secret": "secret", "key": ""}}
    }
    providers = get_social_adapter().list_providers(RequestFactory().get("/"))
    assert [provider.id for provider in providers] == ["google"]
