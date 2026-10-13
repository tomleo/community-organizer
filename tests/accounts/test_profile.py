import datetime

import pytest
from django.core.exceptions import ValidationError

from accounts.models import Profile
from accounts.validators import validate_phone
from organization.models import SiteSettings

pytestmark = pytest.mark.django_db


def _update_settings(**flags):
    site_settings = SiteSettings.load()
    for name, value in flags.items():
        setattr(site_settings, name, value)
    site_settings.save()
    return SiteSettings.load()


def test_profile_created_with_user(make_user):
    user = make_user()
    assert Profile.objects.filter(user=user).count() == 1
    assert user.profile.first_name == ""


def test_defaults_require_name_and_phone(make_user):
    assert make_user().profile.missing_required_fields() == ["first_name", "last_name", "phone"]


def test_complete_profile_has_nothing_missing(complete_user):
    assert complete_user().profile.missing_required_fields() == []


def test_requirements_follow_settings(make_user):
    _update_settings(
        require_name=False,
        require_phone=False,
        require_date_of_birth=True,
        require_address=True,
        require_photo=True,
    )
    profile = make_user().profile

    assert profile.missing_required_fields() == [
        "date_of_birth",
        "address_line1",
        "city",
        "region",
        "postal_code",
        "country",
        "photo",
    ]


def test_address_line2_never_required(make_user):
    _update_settings(require_name=False, require_phone=False, require_address=True)
    profile = make_user().profile
    profile.address_line1, profile.city, profile.region = "1 Main St", "Boston", "MA"
    profile.postal_code, profile.country = "02118", "USA"
    profile.date_of_birth = datetime.date(2000, 1, 1)
    assert profile.missing_required_fields() == []


def test_full_name(make_user):
    profile = make_user().profile
    assert profile.full_name == ""
    profile.first_name = "Ada"
    assert profile.full_name == "Ada"
    profile.last_name = "Lovelace"
    assert profile.full_name == "Ada Lovelace"


@pytest.mark.parametrize("value", ["617-555-0100", "+1 (617) 555.0100", "6175550100"])
def test_phone_accepts(value):
    validate_phone(value)


@pytest.mark.parametrize("value", ["12345", "call me maybe", "1" * 16])
def test_phone_rejects(value):
    with pytest.raises(ValidationError):
        validate_phone(value)
