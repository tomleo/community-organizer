"""Staff-side volunteer data: hours, roles and anonymization."""

from datetime import timedelta

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import (
    Count,
    DurationField,
    Exists,
    ExpressionWrapper,
    F,
    Max,
    OuterRef,
    Q,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.images import RESIZE_SIZES, delete_image
from notifications.models import OutgoingEmail
from organization.roles import ROLE_GROUPS, Role, get_role, set_role
from registrations import services as registration_services
from registrations.models import ACTIVE_STATUSES, Guest, Registration


class VolunteerAdminError(Exception):
    """A staff action on a volunteer that isn't allowed; the message is shown to staff."""


ATTENDED = Q(registrations__status="registered", registrations__attendance="attended")
NO_SHOW = Q(registrations__status="registered", registrations__attendance="no_show")


def volunteer_stats(users, now=None):
    now = now or timezone.now()
    shift_length = ExpressionWrapper(
        F("registrations__position__ends_at") - F("registrations__position__starts_at"),
        output_field=DurationField(),
    )
    return users.annotate(
        hours=Coalesce(Sum(shift_length, filter=ATTENDED), Value(timedelta(0))),
        attended_count=Count("registrations", filter=ATTENDED, distinct=True),
        no_show_count=Count("registrations", filter=NO_SHOW, distinct=True),
        last_shift_at=Max(
            "registrations__position__starts_at",
            filter=Q(
                registrations__status="registered",
                registrations__position__starts_at__lte=now,
            ),
        ),
        has_upcoming=Exists(
            Registration.objects.filter(
                volunteer=OuterRef("pk"),
                status__in=ACTIVE_STATUSES,
                position__starts_at__gt=now,
            )
        ),
    )


def hours_for(user) -> timedelta:
    return volunteer_stats(get_user_model().objects.filter(pk=user.pk)).get().hours


def role_label(user) -> str:
    """Role name from prefetched groups (no query per user)."""
    names = {group.name for group in user.groups.all()}
    if ROLE_GROUPS[Role.ADMIN] in names:
        return Role.ADMIN.label
    if ROLE_GROUPS[Role.COORDINATOR] in names:
        return Role.COORDINATOR.label
    return Role.VOLUNTEER.label


def change_role(actor, user, role) -> None:
    if actor.pk == user.pk:
        raise VolunteerAdminError("You can't change your own role.")
    if user.is_superuser:
        raise VolunteerAdminError("Superusers' roles can't be changed here.")
    set_role(user, Role(role))


PROFILE_TEXT_FIELDS = (
    "first_name",
    "last_name",
    "phone",
    "address_line1",
    "address_line2",
    "city",
    "region",
    "postal_code",
    "country",
    "email_undeliverable_reason",
)


def anonymize(user, *, actor=None) -> None:
    """Erase personal data but keep registrations, so rosters and hours still add up.

    `actor` is the staff member doing it, or None when volunteers delete their own account.
    """
    if user.is_superuser:
        raise VolunteerAdminError("Superuser accounts can't be deleted here.")
    if actor is not None and actor.pk == user.pk:
        raise VolunteerAdminError("Delete your own account from your profile page.")
    if actor is None and get_role(user) == Role.ADMIN:
        raise VolunteerAdminError(
            "Ask another Admin to change your role before deleting your account."
        )

    placeholder = f"deleted-{user.pk}@invalid"
    profile = user.profile
    photo_name = profile.photo.name
    now = timezone.now()
    with transaction.atomic():
        EmailAddress.objects.filter(user=user).delete()
        SocialAccount.objects.filter(user=user).delete()
        user.email = user.username = placeholder
        user.first_name = user.last_name = ""
        user.set_unusable_password()
        user.is_active = False
        user.save()
        user.groups.clear()

        for field in PROFILE_TEXT_FIELDS:
            setattr(profile, field, "")
        profile.date_of_birth = None
        profile.photo = ""
        profile.reminder_emails = profile.announcement_emails = profile.staff_digest = False
        profile.email_undeliverable_at = None
        profile.answers = {}
        profile.deleted_at = now
        profile.save()

        upcoming = Registration.objects.filter(
            volunteer=user, status__in=ACTIVE_STATUSES, position__starts_at__gt=now
        )
        for registration in upcoming:
            registration_services.remove(registration)
        Registration.objects.filter(volunteer=user).update(comments="")
        Guest.objects.filter(registration__volunteer=user).update(
            first_name="Guest", last_name="", relationship="", answers={}
        )
        OutgoingEmail.objects.filter(user=user).update(
            to=placeholder, subject="", text_body="", html_body="", ics=""
        )
        if photo_name:
            transaction.on_commit(lambda: delete_image(photo_name, RESIZE_SIZES))
