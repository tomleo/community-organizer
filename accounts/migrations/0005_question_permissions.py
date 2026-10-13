from django.contrib.auth.management import create_permissions
from django.db import migrations

ROLE_GROUP_NAMES = ["Admin"]
CODENAMES = ["add_profilequestion", "change_profilequestion", "view_profilequestion"]


def grant(apps, schema_editor):
    app_config = apps.get_app_config("accounts")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permissions = Permission.objects.filter(
        content_type__app_label="accounts", codename__in=CODENAMES
    )
    for group in Group.objects.filter(name__in=ROLE_GROUP_NAMES):
        group.permissions.add(*permissions)


def revoke(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permissions = Permission.objects.filter(
        content_type__app_label="accounts", codename__in=CODENAMES
    )
    for group in Group.objects.filter(name__in=ROLE_GROUP_NAMES):
        group.permissions.remove(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_profile_questions"),
        ("organization", "0002_role_groups"),
    ]

    operations = [migrations.RunPython(grant, revoke)]
