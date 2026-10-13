import pytest
from django.urls import reverse

from accounts.models import Profile

pytestmark = pytest.mark.django_db

VALID = {"first_name": "Grace", "last_name": "Hopper", "phone": "617-555-0199"}


def test_incomplete_profile_redirects_to_onboarding(client, make_user):
    client.force_login(make_user())

    response = client.get(reverse("home"))

    assert response.status_code == 302
    assert response.url == f"{reverse('onboarding')}?next=%2F"


def test_complete_profile_is_not_redirected(client, complete_user):
    client.force_login(complete_user())
    assert client.get(reverse("home")).status_code == 200


def test_anonymous_is_not_redirected(client):
    assert client.get(reverse("home")).status_code == 200


@pytest.mark.parametrize("path", ["/onboarding/", "/accounts/email/", "/static/dist/main.css"])
def test_exempt_paths(client, make_user, path):
    client.force_login(make_user())
    response = client.get(path)
    assert not (response.status_code == 302 and response.url.startswith(reverse("onboarding")))


def test_admin_is_exempt(client, make_user):
    client.force_login(make_user())
    response = client.get("/admin/")
    assert not response.url.startswith(reverse("onboarding"))


def test_incomplete_user_can_log_out(client, make_user):
    client.force_login(make_user())
    response = client.post(reverse("account_logout"))
    assert response.status_code == 302
    assert "_auth_user_id" not in client.session


def test_onboarding_completes_and_follows_next(client, make_user):
    user = make_user()
    client.force_login(user)

    response = client.post(f"{reverse('onboarding')}?next=/profile/", VALID)

    assert response.status_code == 302
    assert response.url == "/profile/"
    assert Profile.objects.get(user=user).missing_required_fields() == []


def test_onboarding_ignores_offsite_next(client, make_user):
    client.force_login(make_user())

    response = client.post(f"{reverse('onboarding')}?next=https://evil.example/", VALID)

    assert response.url == reverse("home")


def test_missing_profile_row_is_recreated(client, make_user):
    user = make_user()
    Profile.objects.filter(user=user).delete()
    client.force_login(user)

    response = client.get(reverse("home"))

    assert response.status_code == 302
    assert Profile.objects.filter(user=user).exists()
