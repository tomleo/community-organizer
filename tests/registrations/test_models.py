import pytest
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction

from organization.models import SiteSettings
from registrations.models import ACTIVE_STATUSES, HOLDING_STATUSES, Guest, Registration

pytestmark = pytest.mark.django_db


def test_status_groups():
    assert set(ACTIVE_STATUSES) == {"registered", "waitlisted", "offered"}
    assert set(HOLDING_STATUSES) == {"registered", "offered"}


def test_party_size_counts_guests(volunteer, make_position):
    registration = Registration.objects.create(
        volunteer=volunteer, position=make_position(), status="registered"
    )
    assert registration.party_size == 1
    Guest.objects.create(registration=registration, first_name="Sam", last_name="Lee")
    assert registration.party_size == 2


def test_one_active_registration_per_position(volunteer, make_position):
    position = make_position()
    Registration.objects.create(volunteer=volunteer, position=position, status="registered")
    with pytest.raises(IntegrityError), transaction.atomic():
        Registration.objects.create(volunteer=volunteer, position=position, status="waitlisted")


def test_ended_registrations_do_not_block_new_ones(volunteer, make_position):
    position = make_position()
    Registration.objects.create(volunteer=volunteer, position=position, status="cancelled")
    Registration.objects.create(volunteer=volunteer, position=position, status="registered")
    assert Registration.objects.filter(position=position).count() == 2


def test_is_active(volunteer, make_position):
    registration = Registration(volunteer=volunteer, position=make_position(), status="expired")
    assert registration.is_active is False
    registration.status = "offered"
    assert registration.is_active is True


def test_new_site_settings_defaults():
    site_settings = SiteSettings.load()
    assert site_settings.max_guests == 0
    assert site_settings.offer_window_hours == 24
    assert site_settings.registration_closes_hours_before == 0
    assert site_settings.cancellation_closes_hours_before == 0


def test_offer_window_must_be_at_least_one_hour():
    from django.core.exceptions import ValidationError

    site_settings = SiteSettings.load()
    site_settings.offer_window_hours = 0
    with pytest.raises(ValidationError):
        site_settings.full_clean()


@pytest.mark.parametrize("group_name", ["Coordinator", "Admin"])
def test_groups_get_registration_permissions(group_name):
    codenames = set(
        Group.objects.get(name=group_name).permissions.values_list("codename", flat=True)
    )
    assert {"view_registration", "change_registration"} <= codenames


def test_settings_page_has_registration_fields(client, org_admin):
    client.force_login(org_admin)
    content = client.get("/manage/settings/").content.decode()
    for name in (
        "max_guests",
        "offer_window_hours",
        "registration_closes_hours_before",
        "cancellation_closes_hours_before",
    ):
        assert f'name="{name}"' in content
