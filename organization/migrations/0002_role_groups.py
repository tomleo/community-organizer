from django.contrib.auth.management import create_permissions
from django.db import migrations

ROLE_GROUP_NAMES = ["Coordinator", "Admin"]
ADMIN_PERMISSIONS = [("organization", "change_sitesettings")]


def create_role_groups(apps, schema_editor):
    # Permissions are normally created after migrate finishes; create them now so we can grant them.
    app_config = apps.get_app_config("organization")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for name in ROLE_GROUP_NAMES:
        Group.objects.get_or_create(name=name)
    admin = Group.objects.get(name="Admin")
    for app_label, codename in ADMIN_PERMISSIONS:
        admin.permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )


def remove_role_groups(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name__in=ROLE_GROUP_NAMES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("organization", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(create_role_groups, remove_role_groups)]
