import pytest
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import RequestFactory
from django.utils import timezone

from organization.context_processors import site
from organization.middleware import SiteTimezoneMiddleware
from organization.models import CACHE_KEY, SiteSettings
from organization.permissions import can_manage

pytestmark = pytest.mark.django_db


def test_load_creates_defaults():
    settings_obj = SiteSettings.load()
    assert settings_obj.pk == 1
    assert settings_obj.time_zone == "UTC"
    assert settings_obj.require_name is True
    assert settings_obj.require_phone is True
    assert settings_obj.require_date_of_birth is False
    assert settings_obj.require_address is False
    assert settings_obj.require_photo is False


def test_load_is_cached(django_assert_num_queries):
    SiteSettings.load()
    with django_assert_num_queries(0):
        SiteSettings.load()


def test_save_clears_cache():
    settings_obj = SiteSettings.load()
    settings_obj.org_name = "Neighborhood Pantry"
    settings_obj.save()

    assert cache.get(CACHE_KEY) is None
    assert SiteSettings.load().org_name == "Neighborhood Pantry"


def test_only_one_row_exists():
    SiteSettings(org_name="First").save()
    SiteSettings(org_name="Second").save()
    assert SiteSettings.objects.count() == 1
    assert SiteSettings.load().org_name == "Second"


def test_time_zone_validation():
    settings_obj = SiteSettings(time_zone="Mars/Olympus_Mons")
    with pytest.raises(ValidationError) as excinfo:
        settings_obj.full_clean()
    assert "time_zone" in excinfo.value.message_dict


def test_middleware_activates_site_time_zone():
    settings_obj = SiteSettings.load()
    settings_obj.time_zone = "America/Chicago"
    settings_obj.save()
    middleware = SiteTimezoneMiddleware(
        lambda request: HttpResponse(timezone.get_current_timezone_name())
    )

    response = middleware(RequestFactory().get("/"))

    assert response.content == b"America/Chicago"
    assert timezone.get_current_timezone_name() == "UTC"  # deactivated afterwards


def test_context_processor(django_user_model):
    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    context = site(request)
    assert context["site_settings"].pk == 1
    assert context["can_manage"] is False


def test_can_manage(django_user_model):
    user = django_user_model.objects.create_user(username="u", email="u@example.org")
    assert can_manage(AnonymousUser()) is False
    assert can_manage(user) is False

    user.user_permissions.add(Permission.objects.get(codename="change_sitesettings"))
    user = django_user_model.objects.get(pk=user.pk)
    assert can_manage(user) is True


def test_cache_holds_plain_values_not_a_pickled_model():
    # Pickled model instances outlive deploys (Django upgrades, new fields).
    SiteSettings.load()
    assert isinstance(cache.get(CACHE_KEY), dict)


def test_cache_key_tracks_model_fields():
    field_names = [field.attname for field in SiteSettings._meta.concrete_fields]
    assert CACHE_KEY != "organization:site_settings"
    assert CACHE_KEY == SiteSettings.cache_key_for(field_names)
    assert SiteSettings.cache_key_for([*field_names, "new_field"]) != CACHE_KEY


def test_cache_entry_expires(monkeypatch):
    timeouts = []
    original_set = cache.set
    monkeypatch.setattr(
        cache,
        "set",
        lambda key, value, timeout=None: (
            timeouts.append(timeout) or original_set(key, value, timeout)
        ),
    )
    SiteSettings.load()
    assert timeouts and timeouts[0] is not None and 0 < timeouts[0] <= 600


def test_cached_instance_behaves_like_a_database_row():
    SiteSettings.load()
    cached = SiteSettings.load()
    assert cached._state.adding is False
    assert not cached.logo
    cached.org_name = "From cache"
    cached.save()
    assert SiteSettings.objects.get().org_name == "From cache"
