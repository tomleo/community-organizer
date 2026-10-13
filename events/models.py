from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone

from core.fields import RichTextField
from core.images import validate_image_upload
from events.querysets import EventQuerySet

EVENT_PHOTO_LIMIT = 10
EVENT_PHOTO_SIZES = (1600, 800)


class EventStateError(Exception):
    """An event status change that isn't allowed; the message is shown to staff."""


class Location(models.Model):
    """A reusable venue (schema.org Place with a PostalAddress)."""

    name = models.CharField(max_length=200)
    address_line1 = models.CharField("address line 1", max_length=200)
    address_line2 = models.CharField("address line 2", max_length=200, blank=True)
    city = models.CharField(max_length=100)
    region = models.CharField("state / province / region", max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    notes = models.TextField(
        blank=True, help_text="Shown to volunteers, e.g. parking or entrance details."
    )
    map_url = models.URLField("map link", blank=True)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValidationError("Enter both latitude and longitude, or neither.")

    def events_using(self):
        """Events that use this location, directly or through one of their positions."""
        return Event.objects.filter(Q(location=self) | Q(positions__location=self)).distinct()


class Event(models.Model):
    """A volunteer event (schema.org Event). Its dates come from its positions."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        CANCELLED = "cancelled", "Cancelled"

    title = models.CharField(max_length=200)
    description = RichTextField(blank=True)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="events")
    resources_url = models.URLField("resources link", blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    pinned = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = EventQuerySet.as_manager()

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("event_detail", args=[self.pk])

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    @property
    def is_public(self) -> bool:
        return (
            self.status in (self.Status.PUBLISHED, self.Status.CANCELLED) and not self.is_archived
        )

    def publish(self):
        if self.status != self.Status.DRAFT:
            raise EventStateError("Only drafts can be published.")
        if not self.positions.exists():
            raise EventStateError("Add a position before publishing.")
        self._save_fields(status=self.Status.PUBLISHED)

    def cancel(self):
        if self.status != self.Status.PUBLISHED:
            raise EventStateError("Only published events can be cancelled.")
        self._save_fields(status=self.Status.CANCELLED)

    def reinstate(self):
        if self.status != self.Status.CANCELLED:
            raise EventStateError("Only cancelled events can be reinstated.")
        self._save_fields(status=self.Status.PUBLISHED)

    def archive(self):
        if self.archived_at is None:
            self._save_fields(archived_at=timezone.now())

    def restore(self):
        self._save_fields(archived_at=None)

    def pin(self):
        self._save_fields(pinned=True)

    def unpin(self):
        self._save_fields(pinned=False)

    def _save_fields(self, **values):
        for name, value in values.items():
            setattr(self, name, value)
        self.save(update_fields=[*values, "updated_at"])


class Position(models.Model):
    """A shift within an event (schema.org subEvent)."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="positions")
    title = models.CharField(max_length=200)
    description = RichTextField(blank=True)
    starts_at = models.DateTimeField("starts")
    ends_at = models.DateTimeField("ends")
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="positions",
        help_text="Leave empty to use the event's location.",
    )
    slots = models.PositiveIntegerField("spots", validators=[MinValueValidator(1)])
    schedule_version = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["starts_at", "title"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")), name="position_ends_after_start"
            ),
            models.CheckConstraint(condition=Q(slots__gte=1), name="position_has_slots"),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "The end must be after the start."})

    @property
    def effective_location(self) -> Location:
        return self.location or self.event.location

    @property
    def can_delete(self) -> bool:
        return self.event.status == Event.Status.DRAFT


class EventPhoto(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="events/", validators=[validate_image_upload])
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"Photo {self.position + 1} of {self.event}"
