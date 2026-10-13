from django.contrib.auth.models import Group
from django.db import models, transaction


class Role(models.TextChoices):
    VOLUNTEER = "volunteer", "Volunteer"
    COORDINATOR = "coordinator", "Coordinator"
    ADMIN = "admin", "Admin"


# Volunteers have no group. Group names must match migration 0002_role_groups.
ROLE_GROUPS = {Role.COORDINATOR: "Coordinator", Role.ADMIN: "Admin"}


def get_role(user) -> Role:
    names = set(user.groups.filter(name__in=ROLE_GROUPS.values()).values_list("name", flat=True))
    if ROLE_GROUPS[Role.ADMIN] in names:
        return Role.ADMIN
    if ROLE_GROUPS[Role.COORDINATOR] in names:
        return Role.COORDINATOR
    return Role.VOLUNTEER


def set_role(user, role: Role) -> None:
    with transaction.atomic():
        user.groups.remove(*Group.objects.filter(name__in=ROLE_GROUPS.values()))
        if role != Role.VOLUNTEER:
            user.groups.add(Group.objects.get(name=ROLE_GROUPS[role]))
    # ModelBackend caches permissions on the user instance.
    for attr in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
        user.__dict__.pop(attr, None)
