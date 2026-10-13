from django.urls import reverse

# Entries in the navbar's Manage menu: (label, URL name, permission needed to see it).
# Later parts add their own entries.
MANAGEMENT_LINKS = [
    ("Events", "manage_events", "events.change_event"),
    ("Locations", "manage_locations", "events.change_location"),
    ("Volunteers", "manage_volunteers", "accounts.view_profile"),
    ("Messages", "manage_messages", "notifications.view_message"),
    ("Site settings", "manage_settings", "organization.change_sitesettings"),
    ("Profile questions", "manage_questions", "accounts.change_profilequestion"),
    ("Email log", "manage_emails", "notifications.view_outgoingemail"),
]


def management_links(user) -> list[dict]:
    if not user.is_authenticated:
        return []
    return [
        {"label": label, "url": reverse(url_name)}
        for label, url_name, permission in MANAGEMENT_LINKS
        if user.has_perm(permission)
    ]


def can_manage(user) -> bool:
    return bool(management_links(user))
