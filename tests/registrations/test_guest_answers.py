import pytest
from django.urls import reverse

from accounts.models import ProfileQuestion
from organization.models import SiteSettings
from registrations import services
from registrations.models import Guest, Registration
from registrations.services import GuestData

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def allow_guests():
    site_settings = SiteSettings.load()
    site_settings.max_guests = 2
    site_settings.save()


@pytest.fixture
def spanish():
    return ProfileQuestion.objects.create(label="I speak Spanish", ask_guests=True)


@pytest.fixture
def car():
    return ProfileQuestion.objects.create(label="I have a car", ask_guests=False, order=1)


def guest_post(rows, total, initial=0):
    data = {
        "comments": "",
        "guests-TOTAL_FORMS": str(total),
        "guests-INITIAL_FORMS": str(initial),
        "guests-MIN_NUM_FORMS": "0",
        "guests-MAX_NUM_FORMS": str(total),
    }
    for index in range(total):
        first, last, relationship, ticked = rows[index] if index < len(rows) else ("", "", "", ())
        data.update(
            {
                f"guests-{index}-first_name": first,
                f"guests-{index}-last_name": last,
                f"guests-{index}-relationship": relationship,
            }
        )
        for question in ticked:
            data[f"guests-{index}-question_{question.pk}"] = "on"
    return data


def test_only_guest_questions_on_guest_rows(client, volunteer, make_position, spanish, car):
    client.force_login(volunteer)
    page = client.get(reverse("register", args=[make_position(slots=5).pk])).content.decode()
    assert f"guests-0-question_{spanish.pk}" in page
    assert f"guests-0-question_{car.pk}" not in page


def test_guest_answers_saved(client, volunteer, make_position, spanish):
    position = make_position(slots=5)
    client.force_login(volunteer)
    client.post(
        reverse("register", args=[position.pk]), guest_post([("Sam", "Lee", "Son", (spanish,))], 2)
    )
    guest = Guest.objects.get()
    assert guest.answers == {str(spanish.pk): True}


def test_ticked_question_without_name_is_not_a_guest(client, volunteer, make_position, spanish):
    position = make_position(slots=5)
    client.force_login(volunteer)
    client.post(reverse("register", args=[position.pk]), guest_post([("", "", "", (spanish,))], 2))
    assert Registration.objects.get(volunteer=volunteer).party_size == 1


def test_edit_keeps_guest_answers(client, volunteer, make_position, spanish):
    registration = services.register(
        volunteer,
        make_position(slots=5),
        guests=[GuestData("Sam", "Lee", "Son", {str(spanish.pk): True})],
    )
    client.force_login(volunteer)
    form = client.get(reverse("registration", args=[registration.pk])).context["form"]
    assert form.guest_formset.forms[0][f"question_{spanish.pk}"].value() is True
    client.post(
        reverse("registration", args=[registration.pk]),
        {**guest_post([("Sam", "Lee", "Son", (spanish,))], 2, initial=1), "comments": "updated"},
    )
    assert Guest.objects.get().answers == {str(spanish.pk): True}


def test_guests_turned_off_keeps_answers(volunteer, make_position, spanish):
    registration = services.register(
        volunteer,
        make_position(slots=5),
        guests=[GuestData("Sam", "Lee", "Son", {str(spanish.pk): True})],
    )
    services.update(registration, None, "comment only")
    assert Guest.objects.get().answers == {str(spanish.pk): True}


def test_roster_badges(client, coordinator, volunteer, make_position, spanish):
    volunteer.profile.answers = {str(spanish.pk): True}
    volunteer.profile.save()
    position = make_position(slots=5)
    services.register(
        volunteer, position, guests=[GuestData("Sam", "Lee", "Son", {str(spanish.pk): True})]
    )
    client.force_login(coordinator)
    content = client.get(reverse("manage_roster", args=[position.pk])).content.decode()
    assert content.count("I speak Spanish") >= 2  # volunteer and guest


def test_anonymize_clears_guest_answers(volunteer, make_position, spanish):
    from volunteers.services import anonymize

    position = make_position(starts_in_hours=-48, slots=5)
    registration = Registration.objects.create(
        volunteer=volunteer, position=position, status="registered"
    )
    Guest.objects.create(
        registration=registration,
        first_name="Sam",
        last_name="Lee",
        answers={str(spanish.pk): True},
    )
    anonymize(volunteer)
    assert Guest.objects.get().answers == {}


@pytest.mark.parametrize("change", ["archive", "stop_asking_guests"])
def test_edit_keeps_guest_answers_to_hidden_questions(
    client, volunteer, make_position, spanish, change
):
    registration = services.register(
        volunteer,
        make_position(slots=5),
        guests=[GuestData("Sam", "Lee", "Son", {str(spanish.pk): True})],
    )
    if change == "archive":
        spanish.archived_at = spanish.created_at
    else:
        spanish.ask_guests = False
    spanish.save()
    client.force_login(volunteer)
    client.post(
        reverse("registration", args=[registration.pk]),
        {**guest_post([("Sam", "Lee", "Son", ())], 2, initial=1), "comments": "updated"},
    )
    assert Guest.objects.get().answers == {str(spanish.pk): True}
