from django.conf import settings
from django.db import models

from accounts.requirements import required_profile_fields
from accounts.validators import validate_phone
from core.images import validate_image_upload


class Profile(models.Model):
    """Volunteer information. Every field is optional; SiteSettings decides what is required."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=32, blank=True, validators=[validate_phone])
    date_of_birth = models.DateField(null=True, blank=True)
    address_line1 = models.CharField("address line 1", max_length=200, blank=True)
    address_line2 = models.CharField("address line 2", max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    region = models.CharField("state / province / region", max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, blank=True)
    photo = models.ImageField(upload_to="profiles/", blank=True, validators=[validate_image_upload])
    reminder_emails = models.BooleanField("email me shift reminders", default=True)
    staff_digest = models.BooleanField("send me a daily digest", default=False)
    announcement_emails = models.BooleanField(
        "email me announcements from the organizers", default=True
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    answers = models.JSONField(default=dict, blank=True)
    email_undeliverable_at = models.DateTimeField(null=True, blank=True)
    email_undeliverable_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name or self.user.email

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part)

    def missing_required_fields(self, site_settings=None) -> list[str]:
        if site_settings is None:
            from organization.models import SiteSettings

            site_settings = SiteSettings.load()
        return [name for name in required_profile_fields(site_settings) if not getattr(self, name)]


class ProfileQuestion(models.Model):
    """An organization-defined yes/no question for volunteers (and optionally their guests)."""

    label = models.CharField(max_length=200)
    help_text = models.CharField(max_length=300, blank=True)
    ask_guests = models.BooleanField("also ask about guests", default=False)
    order = models.PositiveIntegerField(default=0)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.label
