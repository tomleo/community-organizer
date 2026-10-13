from django.conf import settings
from django.db import models
from django.db.models import Q


class Registration(models.Model):
    """One volunteer's party (them plus guests) for one position."""

    class Status(models.TextChoices):
        REGISTERED = "registered", "Registered"
        WAITLISTED = "waitlisted", "Waitlisted"
        OFFERED = "offered", "Offered a spot"
        CANCELLED = "cancelled", "Cancelled"
        REMOVED = "removed", "Removed"
        EXPIRED = "expired", "Offer expired"

    class Attendance(models.TextChoices):
        NOT_MARKED = "", "Not marked"
        ATTENDED = "attended", "Attended"
        NO_SHOW = "no_show", "No-show"

    volunteer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="registrations"
    )
    position = models.ForeignKey(
        "events.Position", on_delete=models.CASCADE, related_name="registrations"
    )
    status = models.CharField(max_length=20, choices=Status.choices)
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    waitlisted_at = models.DateTimeField(null=True, blank=True)
    offered_at = models.DateTimeField(null=True, blank=True)
    offer_expires_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    attendance = models.CharField(max_length=10, choices=Attendance.choices, blank=True, default="")
    attendance_marked_at = models.DateTimeField(null=True, blank=True)
    attendance_marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["volunteer", "position"],
                condition=Q(status__in=["registered", "waitlisted", "offered"]),
                name="one_active_registration",
            )
        ]
        indexes = [models.Index(fields=["position", "status"])]

    def __str__(self):
        return f"{self.volunteer} · {self.position} ({self.get_status_display()})"

    @property
    def party_size(self) -> int:
        return 1 + self.guests.count()

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES


ACTIVE_STATUSES = (
    Registration.Status.REGISTERED,
    Registration.Status.WAITLISTED,
    Registration.Status.OFFERED,
)
HOLDING_STATUSES = (Registration.Status.REGISTERED, Registration.Status.OFFERED)


class Guest(models.Model):
    """Someone a volunteer brings who doesn't have an account."""

    registration = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name="guests")
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    relationship = models.CharField(max_length=100, blank=True)
    answers = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
