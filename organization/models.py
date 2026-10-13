import hashlib
from zoneinfo import available_timezones

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from core.fields import RichTextField
from core.images import validate_image_upload

# Short enough that changes made outside save() (data migrations, .update()) show up soon.
CACHE_TIMEOUT = 300
HOME_IMAGE_SIZES = (1600, 800)  # longest side, in pixels
ABOUT_IMAGE_SIZES = (800,)


def validate_time_zone(value):
    if value not in available_timezones():
        raise ValidationError(
            "%(value)s is not a recognized time zone.",
            code="invalid_time_zone",
            params={"value": value},
        )


class SiteSettings(models.Model):
    """Organization-level settings edited by Admins. Exactly one row (pk=1)."""

    org_name = models.CharField("organization name", max_length=200, default="Community Organizer")
    contact_email = models.EmailField(blank=True)
    website_url = models.URLField("website URL", blank=True)
    logo = models.ImageField(upload_to="site/", blank=True, validators=[validate_image_upload])
    time_zone = models.CharField(max_length=64, default="UTC", validators=[validate_time_zone])
    footer_note = models.CharField(
        max_length=300, blank=True, help_text="Shown in every page's footer."
    )
    home_headline = models.CharField(
        max_length=200,
        blank=True,
        help_text="Large heading on the home page. Defaults to the organization name.",
    )
    home_intro = RichTextField(blank=True)
    home_image = models.ImageField(
        upload_to="site/", blank=True, validators=[validate_image_upload]
    )
    about_title = models.CharField(max_length=100, default="About us")
    about_body = RichTextField(
        blank=True, help_text="The About section is hidden while this is empty."
    )
    about_image = models.ImageField(
        upload_to="site/", blank=True, validators=[validate_image_upload]
    )
    require_name = models.BooleanField("require first and last name", default=True)
    require_phone = models.BooleanField(default=True)
    require_date_of_birth = models.BooleanField(default=False)
    require_address = models.BooleanField(default=False)
    require_photo = models.BooleanField(default=False)
    max_guests = models.PositiveIntegerField(
        "guests per registration",
        default=0,
        validators=[MaxValueValidator(50)],
        help_text="How many guests a volunteer may bring. 0 turns guests off.",
    )
    offer_window_hours = models.PositiveIntegerField(
        "waitlist offer window (hours)",
        default=24,
        validators=[MinValueValidator(1)],
        help_text="How long a volunteer has to accept a spot offered from the waitlist.",
    )
    registration_closes_hours_before = models.PositiveIntegerField(
        "registration closes (hours before start)", default=0
    )
    cancellation_closes_hours_before = models.PositiveIntegerField(
        "cancellation closes (hours before start)", default=0
    )
    reminder_hours_before = models.PositiveIntegerField(
        "send reminders (hours before start)",
        default=24,
        help_text="0 turns reminder emails off.",
    )

    class Meta:
        verbose_name = "site settings"
        verbose_name_plural = "site settings"
        permissions = [("manage_roles", "Can change volunteers' roles")]

    def __str__(self):
        return self.org_name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY)

    @staticmethod
    def cache_key_for(field_names) -> str:
        """Cache key that changes whenever the model's fields change, so old entries are ignored."""
        digest = hashlib.sha256(",".join(field_names).encode()).hexdigest()[:12]
        return f"organization:site_settings:{digest}"

    @classmethod
    def load(cls) -> "SiteSettings":
        # Cache plain field values rather than a pickled instance, which can outlive a deploy.
        field_names = [field.attname for field in cls._meta.concrete_fields]
        values = cache.get(CACHE_KEY)
        if values is not None:
            return cls.from_db(None, field_names, [values[name] for name in field_names])
        site_settings, _ = cls.objects.get_or_create(pk=1)
        values = {name: getattr(site_settings, name) for name in field_names}
        for field in cls._meta.concrete_fields:
            if isinstance(field, models.FileField):
                values[field.attname] = getattr(site_settings, field.attname).name or ""
        cache.set(CACHE_KEY, values, timeout=CACHE_TIMEOUT)
        return site_settings


CACHE_KEY = SiteSettings.cache_key_for(
    [field.attname for field in SiteSettings._meta.concrete_fields]
)


class BackupRun(models.Model):
    """One attempt at an off-site backup (core/backups.py)."""

    class Kind(models.TextChoices):
        NIGHTLY = "nightly", "Nightly"
        MANUAL = "manual", "Manual"

    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    ok = models.BooleanField(default=False)
    step = models.CharField(max_length=20, blank=True)
    message = models.TextField(blank=True)
    snapshot_id = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        outcome = "ok" if self.ok else self.step
        return f"{self.kind} backup at {self.started_at:%Y-%m-%d %H:%M} ({outcome})"
