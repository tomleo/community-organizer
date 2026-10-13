import pytest
from django.contrib.auth.models import Group

from organization.roles import Role, get_role, set_role

pytestmark = pytest.mark.django_db


def test_role_groups_exist_with_permissions():
    admin = Group.objects.get(name="Admin")
    coordinator = Group.objects.get(name="Coordinator")
    assert admin.permissions.filter(codename="change_sitesettings").exists()
    assert not coordinator.permissions.filter(codename="change_sitesettings").exists()


def test_new_user_is_volunteer(make_user):
    assert get_role(make_user()) == Role.VOLUNTEER


def test_set_role_keeps_a_single_role_group(make_user):
    user = make_user()
    set_role(user, Role.COORDINATOR)
    set_role(user, Role.ADMIN)

    assert get_role(user) == Role.ADMIN
    assert list(user.groups.values_list("name", flat=True)) == ["Admin"]


def test_set_role_volunteer_removes_role_groups_only(make_user):
    user = make_user()
    other = Group.objects.create(name="Newsletter")
    user.groups.add(other)
    set_role(user, Role.ADMIN)

    set_role(user, Role.VOLUNTEER)

    assert get_role(user) == Role.VOLUNTEER
    assert list(user.groups.values_list("name", flat=True)) == ["Newsletter"]


def test_set_role_refreshes_permission_cache(make_user):
    user = make_user()
    assert not user.has_perm("organization.change_sitesettings")

    set_role(user, Role.ADMIN)

    assert user.has_perm("organization.change_sitesettings")


def test_superuser_has_every_permission(django_user_model):
    superuser = django_user_model.objects.create_superuser(
        username="root", email="root@example.org", password="x"
    )
    assert superuser.has_perm("organization.change_sitesettings")
