import pytest
from django.urls import reverse

from accounts.adapters import AccountAdapter
from tests.constants import PASSWORD

pytestmark = pytest.mark.django_db


def test_signup_verify_onboard_profile(client, monkeypatch, mailoutbox):
    monkeypatch.setattr(AccountAdapter, "generate_email_verification_code", lambda self: "ABC123")

    response = client.post(
        reverse("account_signup"),
        {"email": "new@example.org", "password1": PASSWORD, "password2": PASSWORD},
    )
    assert response.url == reverse("account_email_verification_sent")
    assert "ABC123" in mailoutbox[0].body

    response = client.post(reverse("account_email_verification_sent"), {"code": "ABC123"})
    assert response.status_code == 302
    assert "_auth_user_id" in client.session

    response = client.get(reverse("home"))
    assert response.url == f"{reverse('onboarding')}?next=%2F"

    response = client.post(
        f"{reverse('onboarding')}?next=/",
        {"first_name": "New", "last_name": "Volunteer", "phone": "617-555-0123"},
    )
    assert response.url == "/"

    content = client.get(reverse("profile")).content.decode()
    assert "New Volunteer" in content
    assert "new@example.org" in content
