from django.contrib.auth.management import create_permissions
from django.db import migrations


def grant(apps, schema_editor):
    app_config = apps.get_app_config("notifications")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permission = Permission.objects.get(
        content_type__app_label="notifications", codename="view_outgoingemail"
    )
    for group in Group.objects.filter(name="Admin"):
        group.permissions.add(permission)


def revoke(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permissions = Permission.objects.filter(content_type__app_label="notifications")
    for group in Group.objects.filter(name="Admin"):
        group.permissions.remove(*permissions)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0001_initial"), ("organization", "0002_role_groups")]
    operations = [migrations.RunPython(grant, revoke)]
