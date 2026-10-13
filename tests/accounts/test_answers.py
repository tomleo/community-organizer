import pytest
from django.urls import reverse

from accounts.models import Profile, ProfileQuestion
from volunteers.services import anonymize

pytestmark = pytest.mark.django_db

VALID = {"first_name": "Ada", "last_name": "Lovelace", "phone": "617-555-0100"}


@pytest.fixture
def spanish():
    return ProfileQuestion.objects.create(label="I speak Spanish")


def test_profile_form_saves_answers(client, volunteer, spanish):
    client.force_login(volunteer)
    assert f'name="question_{spanish.pk}"' in client.get(reverse("profile_edit")).content.decode()
    client.post(reverse("profile_edit"), {**VALID, f"question_{spanish.pk}": "on"})
    assert Profile.objects.get(user=volunteer).answers == {str(spanish.pk): True}
    client.post(reverse("profile_edit"), VALID)
    assert Profile.objects.get(user=volunteer).answers == {str(spanish.pk): False}


def test_onboarding_asks_questions(client, make_user, spanish):
    client.force_login(make_user("new@example.org"))
    assert f'name="question_{spanish.pk}"' in client.get(reverse("onboarding")).content.decode()


def test_archived_answers_kept_and_restored(client, volunteer, spanish):
    client.force_login(volunteer)
    client.post(reverse("profile_edit"), {**VALID, f"question_{spanish.pk}": "on"})
    spanish.archived_at = spanish.created_at
    spanish.save()
    content = client.get(reverse("profile_edit")).content.decode()
    assert f'name="question_{spanish.pk}"' not in content
    client.post(reverse("profile_edit"), VALID)  # saving without the archived question
    assert Profile.objects.get(user=volunteer).answers == {str(spanish.pk): True}


def test_unknown_question_ids_ignored(client, volunteer, spanish):
    client.force_login(volunteer)
    client.post(reverse("profile_edit"), {**VALID, "question_99999": "on"})
    assert "99999" not in Profile.objects.get(user=volunteer).answers


def test_volunteer_page_shows_answers(client, coordinator, volunteer, spanish):
    volunteer.profile.answers = {str(spanish.pk): True}
    volunteer.profile.save()
    client.force_login(coordinator)
    content = client.get(reverse("manage_volunteer", args=[volunteer.pk])).content.decode()
    assert "I speak Spanish" in content and "Yes" in content


def test_directory_filter(client, coordinator, make_volunteer, spanish):
    yes, no, _never = make_volunteer(1), make_volunteer(2), make_volunteer(3)
    yes.profile.answers = {str(spanish.pk): True}
    yes.profile.save()
    no.profile.answers = {str(spanish.pk): False}
    no.profile.save()
    client.force_login(coordinator)
    yes_page = client.get(reverse("manage_volunteers"), {f"q_{spanish.pk}": "yes"}).content.decode()
    no_page = client.get(reverse("manage_volunteers"), {f"q_{spanish.pk}": "no"}).content.decode()
    assert "vol1@" in yes_page and "vol2@" not in yes_page and "vol3@" not in yes_page
    assert "vol1@" not in no_page and "vol2@" in no_page and "vol3@" in no_page


def test_anonymize_clears_answers(volunteer, spanish):
    volunteer.profile.answers = {str(spanish.pk): True}
    volunteer.profile.save()
    anonymize(volunteer)
    assert Profile.objects.get(user=volunteer).answers == {}
