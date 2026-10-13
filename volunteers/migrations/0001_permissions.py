from django.contrib.auth.management import create_permissions
from django.db import migrations

GRANTS = {
    "Coordinator": [
        ("accounts", "view_profile"),
        ("notifications", "add_message"),
        ("notifications", "view_message"),
    ],
    "Admin": [
        ("accounts", "view_profile"),
        ("accounts", "delete_profile"),
        ("organization", "manage_roles"),
        ("notifications", "add_message"),
        ("notifications", "view_message"),
    ],
}


def grant(apps, schema_editor):
    for label in ("accounts", "notifications", "organization"):
        app_config = apps.get_app_config(label)
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for group_name, perms in GRANTS.items():
        group = Group.objects.filter(name=group_name).first()
        if group is None:
            continue
        for app_label, codename in perms:
            group.permissions.add(
                Permission.objects.get(content_type__app_label=app_label, codename=codename)
            )


def revoke(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for group_name, perms in GRANTS.items():
        group = Group.objects.filter(name=group_name).first()
        if group is None:
            continue
        for app_label, codename in perms:
            group.permissions.remove(
                *Permission.objects.filter(content_type__app_label=app_label, codename=codename)
            )


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("accounts", "0003_profile_announcement_emails_profile_deleted_at"),
        ("notifications", "0004_outgoingemail_reply_to_alter_outgoingemail_kind_and_more"),
        ("organization", "0005_alter_sitesettings_options"),
    ]

    operations = [migrations.RunPython(grant, revoke)]
