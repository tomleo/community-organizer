import pytest
from django.urls import reverse
from django.utils import timezone

from notifications import group
from notifications.models import Message, OutgoingEmail
from notifications.tasks import send_message
from registrations.models import Registration

pytestmark = pytest.mark.django_db


def test_volunteer_audience_skips_opt_outs_deleted_and_undeliverable(make_volunteer):
    keep, opted_out, deleted, bounced = (make_volunteer(n) for n in range(1, 5))
    opted_out.profile.announcement_emails = False
    opted_out.profile.save()
    deleted.profile.deleted_at = timezone.now()
    deleted.profile.save()
    bounced.profile.email_undeliverable_at = timezone.now()
    bounced.profile.save()

    audience = group.audience_for_volunteers([u.pk for u in (keep, opted_out, deleted, bounced)])

    assert [u.pk for u in audience.users] == [keep.pk]
    assert audience.skipped == {"opted out": 1, "deleted": 1, "undeliverable": 1}
    assert audience.skipped_total == 3


def test_roster_audience_ignores_opt_out_and_filters_statuses(make_volunteer, make_position):
    position = make_position()
    registered, waiting = make_volunteer(1), make_volunteer(2)
    registered.profile.announcement_emails = False
    registered.profile.save()
    Registration.objects.create(volunteer=registered, position=position, status="registered")
    Registration.objects.create(
        volunteer=waiting, position=position, status="waitlisted", waitlisted_at=timezone.now()
    )

    assert [u.pk for u in group.audience_for_position(position, ["registered"]).users] == [
        registered.pk
    ]
    both = group.audience_for_position(position, ["registered", "waitlisted"])
    assert {u.pk for u in both.users} == {registered.pk, waiting.pk}
    assert "Shift" in both.description


def test_event_audience_one_copy_per_volunteer(volunteer, make_position, make_event):
    event = make_event(positions=())
    for hours in (24, 30):
        Registration.objects.create(
            volunteer=volunteer,
            position=make_position(event=event, starts_in_hours=hours),
            status="registered",
        )
    assert [u.pk for u in group.audience_for_event(event, ["registered"]).users] == [volunteer.pk]


def test_send_message_task(
    make_volunteer, coordinator, mailoutbox, django_capture_on_commit_callbacks
):
    first, second = make_volunteer(1), make_volunteer(2)
    audience = group.audience_for_volunteers([first.pk, second.pk])
    with django_capture_on_commit_callbacks(execute=True):
        message = group.create_message(
            coordinator, "Parking update", "Use the back lot.\nThanks!", audience
        )
    assert message.recipient_count == 2
    emails = OutgoingEmail.objects.filter(message=message)
    assert emails.count() == 2
    assert {e.kind for e in emails} == {"message"}
    assert all(e.reply_to == coordinator.email for e in emails)
    assert "Use the back lot." in emails.first().text_body


def test_recipient_who_becomes_undeliverable_is_suppressed(make_volunteer, coordinator):
    person = make_volunteer(1)
    audience = group.audience_for_volunteers([person.pk])
    message = Message.objects.create(
        sender=coordinator, subject="s", body="b", audience="x", recipient_count=1
    )
    person.profile.email_undeliverable_at = timezone.now()
    person.profile.save()
    send_message(message.pk, [u.pk for u in audience.users])
    assert OutgoingEmail.objects.get(message=message).status == "suppressed"


def test_compose_preview_send(
    client, coordinator, make_volunteer, django_capture_on_commit_callbacks
):
    first, second = make_volunteer(1), make_volunteer(2)
    second.profile.announcement_emails = False
    second.profile.save()
    client.force_login(coordinator)
    url = reverse("manage_message_new")
    params = {"ids": [first.pk, second.pk]}
    assert client.get(url, params).status_code == 200

    preview = client.post(
        url + f"?ids={first.pk}&ids={second.pk}",
        {"subject": "Hi", "body": "Hello", "step": "preview"},
    )
    content = preview.content.decode()
    assert "Send to 1 volunteer" in content
    assert "1 skipped" in content

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            url + f"?ids={first.pk}&ids={second.pk}",
            {"subject": "Hi", "body": "Hello", "step": "send"},
            follow=True,
        )
    message = Message.objects.get()
    assert response.request["PATH_INFO"] == reverse("manage_message", args=[message.pk])
    assert OutgoingEmail.objects.filter(message=message).count() == 1


def test_nobody_to_send_to(client, coordinator, volunteer):
    volunteer.profile.announcement_emails = False
    volunteer.profile.save()
    client.force_login(coordinator)
    response = client.post(
        reverse("manage_message_new") + f"?ids={volunteer.pk}",
        {"subject": "Hi", "body": "x", "step": "send"},
    )
    assert "Nobody to send to" in response.content.decode()
    assert not Message.objects.exists()


def test_permissions_and_history(client, volunteer, coordinator):
    client.force_login(volunteer)
    assert client.get(reverse("manage_message_new")).status_code == 403
    assert client.get(reverse("manage_messages")).status_code == 403
    message = Message.objects.create(
        sender=coordinator,
        subject="Parking",
        body="b",
        audience="Selected volunteers",
        recipient_count=3,
    )
    client.force_login(coordinator)
    assert "Parking" in client.get(reverse("manage_messages")).content.decode()
    assert client.get(reverse("manage_message", args=[message.pk])).status_code == 200


def test_entry_points(client, coordinator, volunteer, make_position):
    position = make_position()
    client.force_login(coordinator)
    new = reverse("manage_message_new")
    assert new in client.get(reverse("manage_volunteers")).content.decode()
    assert (
        f"{new}?ids={volunteer.pk}"
        in client.get(reverse("manage_volunteer", args=[volunteer.pk])).content.decode()
    )
    assert (
        f"{new}?position={position.pk}"
        in client.get(reverse("manage_roster", args=[position.pk])).content.decode()
    )
    assert (
        f"{new}?event={position.event_id}"
        in client.get(reverse("manage_event", args=[position.event_id])).content.decode()
    )


def test_menu_has_messages(coordinator):
    from organization.permissions import management_links

    assert "Messages" in [link["label"] for link in management_links(coordinator)]
