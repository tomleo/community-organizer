import pytest
from django.contrib.auth.models import Group
from django.utils import timezone

from notifications import outbox
from notifications.models import Message, OutgoingEmail
from registrations.models import Registration

pytestmark = pytest.mark.django_db


def codenames(group_name):
    return {
        f"{p.content_type.app_label}.{p.codename}"
        for p in Group.objects.get(name=group_name).permissions.select_related("content_type")
    }


def test_coordinator_permissions():
    perms = codenames("Coordinator")
    assert {
        "accounts.view_profile",
        "notifications.add_message",
        "notifications.view_message",
    } <= perms
    assert "accounts.delete_profile" not in perms
    assert "organization.manage_roles" not in perms


def test_admin_permissions():
    perms = codenames("Admin")
    assert {
        "accounts.view_profile",
        "accounts.delete_profile",
        "organization.manage_roles",
        "notifications.add_message",
        "notifications.view_message",
    } <= perms


def test_defaults(volunteer, make_position):
    registration = Registration.objects.create(
        volunteer=volunteer, position=make_position(), status="registered"
    )
    assert registration.attendance == ""
    assert volunteer.profile.announcement_emails is True
    assert volunteer.profile.deleted_at is None


def test_deleted_users_are_suppressed(volunteer):
    volunteer.profile.deleted_at = timezone.now()
    volunteer.profile.save()
    email = outbox.queue(
        kind="registered", user=volunteer, subject="s", text_body="t", html_body="h"
    )
    assert email.status == "suppressed"


def test_reply_to_on_row_overrides_contact(
    volunteer, mailoutbox, django_capture_on_commit_callbacks
):
    message = Message.objects.create(subject="Hi", body="Body", audience="Test")
    with django_capture_on_commit_callbacks(execute=True):
        email = outbox.queue(
            kind="message",
            user=volunteer,
            subject="s",
            text_body="t",
            html_body="h",
            reply_to="coordinator@example.org",
            message=message,
        )
    assert email.message == message
    assert mailoutbox[0].reply_to == ["coordinator@example.org"]
    assert OutgoingEmail.Kind.MESSAGE == "message"
