from zoneinfo import available_timezones

from django import forms

from organization.models import SiteSettings

# The settings page's sections, in order: (heading, field names).
SECTIONS = [
    (
        "Organization",
        ["org_name", "contact_email", "website_url", "logo", "time_zone", "footer_note"],
    ),
    (
        "Home page",
        ["home_headline", "home_intro", "home_image", "about_title", "about_body", "about_image"],
    ),
    (
        "Volunteer profiles",
        [
            "require_name",
            "require_phone",
            "require_date_of_birth",
            "require_address",
            "require_photo",
        ],
    ),
    (
        "Registration",
        [
            "max_guests",
            "offer_window_hours",
            "registration_closes_hours_before",
            "cancellation_closes_hours_before",
        ],
    ),
    ("Reminders", ["reminder_hours_before"]),
]


class SiteSettingsForm(forms.ModelForm):
    time_zone = forms.ChoiceField(choices=[(tz, tz) for tz in sorted(available_timezones())])

    class Meta:
        model = SiteSettings
        fields = [name for _, names in SECTIONS for name in names]

    def sections(self):
        return [(title, [self[name] for name in names]) for title, names in SECTIONS]
