import pytest
from django.urls import reverse

from organization.models import SiteSettings
from registrations import services
from registrations.models import Registration

pytestmark = pytest.mark.django_db


def guest_data(rows, total):
    data = {
        "guests-TOTAL_FORMS": str(total),
        "guests-INITIAL_FORMS": "0",
        "guests-MIN_NUM_FORMS": "0",
        "guests-MAX_NUM_FORMS": str(total),
    }
    for index in range(total):
        first, last, relationship = rows[index] if index < len(rows) else ("", "", "")
        data[f"guests-{index}-first_name"] = first
        data[f"guests-{index}-last_name"] = last
        data[f"guests-{index}-relationship"] = relationship
    return data


def allow_guests(count):
    site_settings = SiteSettings.load()
    site_settings.max_guests = count
    site_settings.save()


def test_register_requires_login(client, make_position):
    url = reverse("register", args=[make_position().pk])
    response = client.get(url)
    assert response.status_code == 302
    assert response.url.startswith(reverse("account_login"))


def test_register_page_404_for_unpublished(client, volunteer, make_position):
    client.force_login(volunteer)
    assert (
        client.get(reverse("register", args=[make_position(status="draft").pk])).status_code == 404
    )


def test_register(client, volunteer, make_position):
    position = make_position()
    client.force_login(volunteer)
    page = client.get(reverse("register", args=[position.pk])).content.decode()
    assert "You'll be registered" in page or "You&#x27;ll be registered" in page
    response = client.post(reverse("register", args=[position.pk]), {"comments": "Hi"}, follow=True)
    assert "You&#x27;re registered" in response.content.decode()
    assert Registration.objects.get(volunteer=volunteer).status == "registered"


def test_register_full_position_says_waitlist(client, make_volunteer, make_position):
    position = make_position(slots=1)
    services.register(make_volunteer(2), position)
    volunteer = make_volunteer(1)
    client.force_login(volunteer)
    page = client.get(reverse("register", args=[position.pk])).content.decode()
    assert "join the waitlist as #1" in page
    response = client.post(reverse("register", args=[position.pk]), {"comments": ""}, follow=True)
    assert "#1 on the waitlist" in response.content.decode()


def test_no_guest_rows_when_guests_off(client, volunteer, make_position):
    client.force_login(volunteer)
    page = client.get(reverse("register", args=[make_position().pk])).content.decode()
    assert "guests-TOTAL_FORMS" not in page


def test_guest_rows_and_empty_rows_ignored(client, volunteer, make_position):
    allow_guests(3)
    position = make_position(slots=5)
    client.force_login(volunteer)
    page = client.get(reverse("register", args=[position.pk])).content.decode()
    assert page.count("data-guest-row>") == 3
    client.post(
        reverse("register", args=[position.pk]),
        {"comments": "", **guest_data([("Sam", "Lee", "Son")], 3)},
    )
    registration = Registration.objects.get(volunteer=volunteer)
    assert [(g.first_name, g.last_name, g.relationship) for g in registration.guests.all()] == [
        ("Sam", "Lee", "Son")
    ]


def test_partial_guest_row_is_an_error(client, volunteer, make_position):
    allow_guests(2)
    position = make_position(slots=5)
    client.force_login(volunteer)
    response = client.post(
        reverse("register", args=[position.pk]),
        {"comments": "", **guest_data([("Ann", "", "")], 2)},
    )
    assert response.status_code == 200
    assert "This field is required." in response.content.decode()
    assert not Registration.objects.exists()


def test_service_error_shown(client, volunteer, make_position):
    position = make_position()
    services.register(volunteer, position)
    client.force_login(volunteer)
    response = client.post(reverse("register", args=[position.pk]), {"comments": ""}, follow=True)
    assert "already registered" in response.content.decode()


def test_manage_page_only_for_owner(client, make_volunteer, make_position):
    registration = services.register(make_volunteer(1), make_position())
    client.force_login(make_volunteer(2))
    assert client.get(reverse("registration", args=[registration.pk])).status_code == 404


def test_manage_edit(client, volunteer, make_position):
    allow_guests(1)
    registration = services.register(volunteer, make_position(slots=3))
    client.force_login(volunteer)
    client.post(
        reverse("registration", args=[registration.pk]),
        {"comments": "Bringing my son", **guest_data([("Sam", "Lee", "Son")], 1)},
    )
    registration.refresh_from_db()
    assert registration.comments == "Bringing my son"
    assert registration.party_size == 2


def test_cancel(client, volunteer, make_position):
    registration = services.register(volunteer, make_position())
    client.force_login(volunteer)
    assert client.get(reverse("registration_cancel", args=[registration.pk])).status_code == 200
    response = client.post(reverse("registration_cancel", args=[registration.pk]), follow=True)
    assert "Your registration has been cancelled." in response.content.decode()
    registration.refresh_from_db()
    assert registration.status == "cancelled"


def test_cancel_after_cutoff_shows_contact(client, volunteer, make_position):
    site_settings = SiteSettings.load()
    site_settings.cancellation_closes_hours_before = 72
    site_settings.contact_email = "help@org.example"
    site_settings.save()
    registration = services.register(volunteer, make_position(starts_in_hours=48))
    client.force_login(volunteer)
    content = client.get(reverse("registration_cancel", args=[registration.pk])).content.decode()
    assert "Cancellation has closed for this shift" in content
    assert "help@org.example" in content


def offered(make_volunteer, make_position):
    position = make_position(slots=1)
    holder = services.register(make_volunteer(2), position)
    waiter = services.register(make_volunteer(1), position)
    services.cancel(holder)
    waiter.refresh_from_db()
    return waiter


def test_accept_offer(client, make_volunteer, make_position):
    waiter = offered(make_volunteer, make_position)
    client.force_login(waiter.volunteer)
    response = client.post(reverse("registration_accept", args=[waiter.pk]), {"next": "/profile/"})
    assert response.url == "/profile/"
    waiter.refresh_from_db()
    assert waiter.status == "registered"


def test_decline_offer_ignores_offsite_next(client, make_volunteer, make_position):
    waiter = offered(make_volunteer, make_position)
    client.force_login(waiter.volunteer)
    response = client.post(
        reverse("registration_decline", args=[waiter.pk]), {"next": "https://evil.example/"}
    )
    assert response.url == reverse("profile")
    waiter.refresh_from_db()
    assert waiter.status == "cancelled"


def test_accept_requires_post_and_owner(client, make_volunteer, make_position):
    waiter = offered(make_volunteer, make_position)
    client.force_login(make_volunteer(3))
    assert client.post(reverse("registration_accept", args=[waiter.pk])).status_code == 404
    client.force_login(waiter.volunteer)
    assert client.get(reverse("registration_accept", args=[waiter.pk])).status_code == 405
