import pytest
from django.urls import reverse

from accounts.models import ProfileQuestion
from accounts.questions import (
    active_questions,
    answers_from,
    field_name,
    guest_questions,
    yes_labels,
)

pytestmark = pytest.mark.django_db


def make(label, order=0, ask_guests=False):
    return ProfileQuestion.objects.create(label=label, order=order, ask_guests=ask_guests)


def test_helpers():
    spanish = make("I speak Spanish", order=1, ask_guests=True)
    car = make("I have a car", order=0)
    archived = make("Old question", order=2)
    archived.archived_at = archived.created_at
    archived.save()
    assert list(active_questions()) == [car, spanish]
    assert list(guest_questions()) == [spanish]
    assert field_name(spanish) == f"question_{spanish.pk}"
    answers = answers_from({field_name(spanish): True}, [car, spanish])
    assert answers == {str(car.pk): False, str(spanish.pk): True}
    assert yes_labels(answers, [car, spanish]) == ["I speak Spanish"]
    assert yes_labels(None, [car]) == []


def test_admin_only(client, coordinator, org_admin):
    url = reverse("manage_questions")
    client.force_login(coordinator)
    assert client.get(url).status_code == 403
    client.force_login(org_admin)
    assert client.get(url).status_code == 200


def test_create_edit(client, org_admin):
    client.force_login(org_admin)
    make("First", order=0)
    client.post(
        reverse("manage_question_new"),
        {"label": "I speak Spanish", "help_text": "", "ask_guests": "on"},
    )
    question = ProfileQuestion.objects.get(label="I speak Spanish")
    assert question.ask_guests is True
    assert question.order == 1
    client.post(
        reverse("manage_question_edit", args=[question.pk]),
        {"label": "Habla español", "help_text": "x"},
    )
    question.refresh_from_db()
    assert question.label == "Habla español" and question.ask_guests is False


def test_move(client, org_admin):
    first, second = make("A", order=0), make("B", order=1)
    client.force_login(org_admin)
    client.post(reverse("manage_question_move", args=[second.pk, "up"]))
    assert list(active_questions()) == [second, first]


def test_archive_and_restore(client, org_admin):
    question = make("A")
    client.force_login(org_admin)
    client.post(reverse("manage_question_archive", args=[question.pk]))
    assert list(active_questions()) == []
    client.post(reverse("manage_question_restore", args=[question.pk]))
    assert list(active_questions()) == [question]


def test_menu(org_admin, coordinator):
    from organization.permissions import management_links

    assert "Profile questions" in [link["label"] for link in management_links(org_admin)]
    assert "Profile questions" not in [link["label"] for link in management_links(coordinator)]
