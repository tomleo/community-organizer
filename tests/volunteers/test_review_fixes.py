import re

import pytest
from django.urls import reverse

from events.models import Event, Position
from notifications import group
from notifications.models import Message
from registrations.models import Registration

pytestmark = pytest.mark.django_db


def test_sending_the_same_preview_twice_creates_one_message(client, coordinator, volunteer):
    client.force_login(coordinator)
    url = reverse("manage_message_new") + f"?ids={volunteer.pk}"
    preview = client.post(
        url, {"subject": "Hi", "body": "Hello", "step": "preview"}
    ).content.decode()
    token = re.search(r'name="send_token" value="([^"]+)"', preview).group(1)

    first = client.post(
        url, {"subject": "Hi", "body": "Hello", "step": "send", "send_token": token}
    )
    second = client.post(
        url, {"subject": "Hi", "body": "Hello", "step": "send", "send_token": token}
    )

    assert Message.objects.count() == 1
    assert first.url == second.url == reverse("manage_message", args=[Message.objects.get().pk])


def test_long_titles_do_not_break_sending(
    volunteer, coordinator, make_position, django_capture_on_commit_callbacks
):
    position = make_position()
    Position.objects.filter(pk=position.pk).update(title="P" * 200)
    Event.objects.filter(pk=position.event_id).update(title="E" * 200)
    position = Position.objects.select_related("event").get(pk=position.pk)
    Registration.objects.create(volunteer=volunteer, position=position, status="registered")
    audience = group.audience_for_position(position, ["registered", "offered", "waitlisted"])
    with django_capture_on_commit_callbacks(execute=True):
        message = group.create_message(coordinator, "s", "b", audience)
    assert len(message.audience) <= 255


def test_incomplete_profile_can_still_delete_account(client, make_user):
    user = make_user("new@example.org")  # never finished onboarding
    client.force_login(user)
    assert client.get(reverse("account_delete")).status_code == 200
