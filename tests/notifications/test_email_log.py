import pytest
from django.urls import reverse

from notifications.models import OutgoingEmail

pytestmark = pytest.mark.django_db


def make(user, status="sent", subject="Hello"):
    return OutgoingEmail.objects.create(
        to=user.email,
        user=user,
        kind="registered",
        subject=subject,
        text_body="Body text",
        html_body="<p>x</p>",
        status=status,
    )


def test_permissions(client, volunteer, coordinator, org_admin):
    url = reverse("manage_emails")
    assert client.get(url).status_code == 302
    for user, expected in ((volunteer, 403), (coordinator, 403), (org_admin, 200)):
        client.force_login(user)
        assert client.get(url).status_code == expected


def test_filter_and_search(client, org_admin, make_volunteer):
    make(make_volunteer(1), status="bounced", subject="Bounced one")
    make(make_volunteer(2), status="sent", subject="Sent one")
    client.force_login(org_admin)
    bounced = client.get(reverse("manage_emails") + "?status=bounced").content.decode()
    searched = client.get(reverse("manage_emails") + "?q=vol2").content.decode()
    assert "Bounced one" in bounced and "Sent one" not in bounced
    assert "Sent one" in searched and "Bounced one" not in searched


def test_detail_shows_body(client, org_admin, volunteer):
    email = make(volunteer)
    client.force_login(org_admin)
    assert "Body text" in client.get(reverse("manage_email", args=[email.pk])).content.decode()


def test_admin_menu_has_email_log(org_admin, coordinator):
    from organization.permissions import management_links

    assert "Email log" in [link["label"] for link in management_links(org_admin)]
    assert "Email log" not in [link["label"] for link in management_links(coordinator)]
