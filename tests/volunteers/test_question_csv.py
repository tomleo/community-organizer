import csv
import io

import pytest
from django.urls import reverse

from accounts.models import ProfileQuestion
from registrations.models import Guest, Registration

pytestmark = pytest.mark.django_db


def rows(response):
    return list(csv.reader(io.StringIO(response.content.decode("utf-8")[1:])))


def test_directory_columns(client, coordinator, make_volunteer):
    spanish = ProfileQuestion.objects.create(label="I speak Spanish")
    yes, _never = make_volunteer(1), make_volunteer(2)
    yes.profile.answers = {str(spanish.pk): True}
    yes.profile.save()
    client.force_login(coordinator)
    data = rows(client.get(reverse("manage_volunteers_export"), {"q": "vol"}))
    assert data[0][-1] == "I speak Spanish"
    by_email = {row[2]: row[-1] for row in data[1:]}
    assert by_email == {"vol1@example.org": "Yes", "vol2@example.org": "No"}


def test_roster_columns_and_guest_answers(client, coordinator, volunteer, make_position):
    spanish = ProfileQuestion.objects.create(label="I speak Spanish", ask_guests=True)
    position = make_position()
    registration = Registration.objects.create(
        volunteer=volunteer, position=position, status="registered"
    )
    Guest.objects.create(
        registration=registration,
        first_name="Sam",
        last_name="Lee",
        relationship="Son",
        answers={str(spanish.pk): True},
    )
    client.force_login(coordinator)
    data = rows(client.get(reverse("manage_roster_export", args=[position.pk])))
    assert data[0][-1] == "I speak Spanish"
    assert data[1][-1] == "No"
    assert data[1][6] == "Sam Lee (Son; I speak Spanish)"
