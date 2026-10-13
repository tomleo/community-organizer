import csv
import io

import pytest
from django.urls import reverse

from registrations.models import Guest, Registration
from volunteers.csv_export import safe

pytestmark = pytest.mark.django_db


def rows(response):
    text = response.content.decode("utf-8")
    assert text.startswith("﻿")
    return list(csv.reader(io.StringIO(text[1:])))


def test_safe_escapes_formulas():
    assert safe('=HYPERLINK("http://evil")') == '\'=HYPERLINK("http://evil")'
    assert safe("+1 617") == "'+1 617"
    assert safe("-x") == "'-x"
    assert safe("@cmd") == "'@cmd"
    assert safe("Ada") == "Ada"
    assert safe(None) == ""


def test_directory_export_all_matching(client, coordinator, make_volunteer):
    ada = make_volunteer(1)
    ada.profile.first_name = "=HYPERLINK(1)"
    ada.profile.save()
    make_volunteer(2)
    client.force_login(coordinator)
    response = client.get(reverse("manage_volunteers_export"), {"q": "vol1"})
    assert response["Content-Type"].startswith("text/csv")
    data = rows(response)
    assert data[0][:5] == ["First name", "Last name", "Email", "Phone", "Role"]
    assert len(data) == 2
    assert data[1][0] == "'=HYPERLINK(1)"
    assert data[1][2] == "vol1@example.org"


def test_directory_export_selected(client, coordinator, make_volunteer):
    first, second = make_volunteer(1), make_volunteer(2)
    client.force_login(coordinator)
    data = rows(client.get(reverse("manage_volunteers_export"), {"ids": [second.pk]}))
    assert [row[2] for row in data[1:]] == ["vol2@example.org"]
    assert first


def test_directory_export_permission(client, volunteer):
    client.force_login(volunteer)
    assert client.get(reverse("manage_volunteers_export")).status_code == 403


def test_roster_export(client, coordinator, volunteer, make_position):
    position = make_position()
    registration = Registration.objects.create(
        volunteer=volunteer, position=position, status="registered", comments="Hi"
    )
    Guest.objects.create(
        registration=registration, first_name="Sam", last_name="Lee", relationship="Son"
    )
    client.force_login(coordinator)
    data = rows(client.get(reverse("manage_roster_export", args=[position.pk])))
    assert data[0] == [
        "First name",
        "Last name",
        "Email",
        "Phone",
        "Status",
        "Attendance",
        "Guests",
        "Comment",
        "Registered at",
    ]
    assert data[1][2] == "vol1@example.org"
    assert data[1][6] == "Sam Lee (Son)"


def test_export_buttons_present(client, coordinator, volunteer, make_position):
    client.force_login(coordinator)
    assert (
        reverse("manage_volunteers_export")
        in client.get(reverse("manage_volunteers")).content.decode()
    )
    position = make_position()
    assert (
        reverse("manage_roster_export", args=[position.pk])
        in client.get(reverse("manage_roster", args=[position.pk])).content.decode()
    )
