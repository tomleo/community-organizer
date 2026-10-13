from django.contrib.auth.management import create_permissions
from django.db import migrations

ROLE_GROUP_NAMES = ["Coordinator", "Admin"]
MODELS = ["location", "event", "position", "eventphoto"]
ACTIONS = ["add", "change", "delete"]


def grant_event_permissions(apps, schema_editor):
    app_config = apps.get_app_config("events")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permissions = Permission.objects.filter(
        content_type__app_label="events",
        codename__in=[f"{action}_{model}" for model in MODELS for action in ACTIONS],
    )
    for group in Group.objects.filter(name__in=ROLE_GROUP_NAMES):
        group.permissions.add(*permissions)


def revoke_event_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permissions = Permission.objects.filter(content_type__app_label="events")
    for group in Group.objects.filter(name__in=ROLE_GROUP_NAMES):
        group.permissions.remove(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0001_initial"),
        ("organization", "0002_role_groups"),
    ]

    operations = [migrations.RunPython(grant_event_permissions, revoke_event_permissions)]
