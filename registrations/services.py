"""Registration rules. Every registration change goes through these functions.

Each public function runs in a transaction with the position row locked, re-checks the rules,
and raises RegistrationError with a message that can be shown to the user.
"""

from dataclasses import asdict, dataclass, field, replace
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from events.models import Event, Position
from notifications import messages as emails
from organization.models import SiteSettings
from registrations.models import ACTIVE_STATUSES, HOLDING_STATUSES, Guest, Registration

Status = Registration.Status

AUTO_FILL_WINDOW = timedelta(hours=2)
RATE_LIMIT = 10
RATE_WINDOW = timedelta(hours=1)
ALREADY_REGISTERED = "You're already registered for this position."


class RegistrationError(Exception):
    """A registration change that isn't allowed; the message is shown to the user."""


@dataclass(frozen=True)
class GuestData:
    first_name: str
    last_name: str
    relationship: str = ""
    answers: dict = field(default_factory=dict)


# --- Queries -------------------------------------------------------------------------------


def spots_taken(position) -> int:
    holding = Registration.objects.filter(position=position, status__in=HOLDING_STATUSES)
    return holding.count() + Guest.objects.filter(registration__in=holding).count()


def available_spots(position) -> int:
    return position.slots - spots_taken(position)


def is_open(position, now=None) -> bool:
    """Published, not archived, and not started yet."""
    now = now or timezone.now()
    event = position.event
    return (
        event.status == Event.Status.PUBLISHED
        and event.archived_at is None
        and now < position.starts_at
    )


def registration_closes_at(position, site_settings):
    return position.starts_at - timedelta(hours=site_settings.registration_closes_hours_before)


def cancellation_closes_at(position, site_settings):
    return position.starts_at - timedelta(hours=site_settings.cancellation_closes_hours_before)


def waitlist_place(registration) -> int:
    earlier = Registration.objects.filter(
        position_id=registration.position_id,
        status=Status.WAITLISTED,
        waitlisted_at__lt=registration.waitlisted_at,
    )
    return earlier.count() + 1


def _overlaps(volunteer, position) -> bool:
    return (
        Registration.objects.filter(
            volunteer=volunteer,
            status__in=ACTIVE_STATUSES,
            position__starts_at__lt=position.ends_at,
            position__ends_at__gt=position.starts_at,
        )
        .exclude(position_id=position.pk)
        .exists()
    )


# --- Helpers -------------------------------------------------------------------------------


def _lock(position) -> Position:
    return (
        Position.objects.select_related("event").select_for_update(of=("self",)).get(pk=position.pk)
    )


def _check_guests(guests, site_settings):
    limit = site_settings.max_guests
    if guests and limit == 0:
        raise RegistrationError("Guests aren't allowed for this organization.")
    if len(guests) > limit:
        raise RegistrationError(f"You can bring at most {limit} guest{'s' if limit != 1 else ''}.")


def _check_party_fits_position(size, position):
    """A party bigger than the whole position could never get in, so don't waitlist it."""
    if size > position.slots:
        raise RegistrationError(
            f"This position only has {position.slots} spot{'s' if position.slots != 1 else ''}, "
            f"so a party of {size} can't join."
        )


def _set_guests(registration, guests):
    registration.guests.all().delete()
    Guest.objects.bulk_create(
        [Guest(registration=registration, **asdict(guest)) for guest in guests]
    )


def _end(registration, status, now):
    registration.status = status
    registration.ended_at = now
    registration.save(update_fields=["status", "ended_at", "updated_at"])


# --- Volunteer and staff actions ------------------------------------------------------------


def register(volunteer, position, guests=(), comments="", *, by_staff=False) -> Registration:
    guests = list(guests or ())
    site_settings = SiteSettings.load()
    now = timezone.now()
    with transaction.atomic():
        position = _lock(position)
        if not is_open(position, now):
            raise RegistrationError("Registration isn't open for this position.")
        if not by_staff:
            if now >= registration_closes_at(position, site_settings):
                raise RegistrationError("Registration has closed for this position.")
            if volunteer.profile.missing_required_fields(site_settings):
                raise RegistrationError("Please complete your profile before registering.")
            recent = Registration.objects.filter(
                volunteer=volunteer, created_at__gte=now - RATE_WINDOW
            ).count()
            if recent >= RATE_LIMIT:
                raise RegistrationError(
                    "You've signed up for a lot of shifts recently. Please try again in an hour."
                )
        _check_guests(guests, site_settings)
        if Registration.objects.filter(
            volunteer=volunteer, position=position, status__in=ACTIVE_STATUSES
        ).exists():
            raise RegistrationError(ALREADY_REGISTERED)
        if _overlaps(volunteer, position):
            raise RegistrationError("This shift overlaps another shift you're signed up for.")
        _check_party_fits_position(1 + len(guests), position)

        fits = 1 + len(guests) <= available_spots(position)
        registration = Registration(
            volunteer=volunteer,
            position=position,
            comments=comments,
            status=Status.REGISTERED if fits else Status.WAITLISTED,
            waitlisted_at=None if fits else now,
        )
        try:
            with transaction.atomic():
                registration.save()
        except IntegrityError as exc:
            raise RegistrationError(ALREADY_REGISTERED) from exc
        _set_guests(registration, guests)
        if registration.status == Status.REGISTERED:
            emails.registered(registration)
        else:
            emails.waitlisted(registration, waitlist_place(registration))
    return registration


def update(registration, guests, comments) -> Registration:
    """Change guests and comment. `guests=None` keeps the current guests (guests turned off)."""
    site_settings = SiteSettings.load()
    now = timezone.now()
    with transaction.atomic():
        position = _lock(registration.position)
        registration = Registration.objects.select_for_update().get(pk=registration.pk)
        if registration.status not in ACTIVE_STATUSES:
            raise RegistrationError("This registration is no longer active.")
        if registration.status == Status.OFFERED:
            raise RegistrationError("Accept or decline your offer before making changes.")
        if now >= position.starts_at:
            raise RegistrationError("This shift has already started.")
        if guests is None:
            guests = [
                GuestData(
                    guest.first_name, guest.last_name, guest.relationship, dict(guest.answers)
                )
                for guest in registration.guests.all()
            ]
        else:
            # Forms only carry answers to current guest questions; keep the rest (archived, or no
            # longer asked about guests) for guests who are still in the party.
            previous = {(g.first_name, g.last_name): g.answers for g in registration.guests.all()}
            guests = [
                replace(
                    guest,
                    answers={
                        **previous.get((guest.first_name, guest.last_name), {}),
                        **guest.answers,
                    },
                )
                for guest in guests
            ]
            _check_guests(guests, site_settings)
        old_size, new_size = registration.party_size, 1 + len(guests)
        if new_size > old_size:
            if not is_open(position, now) or now >= registration_closes_at(position, site_settings):
                raise RegistrationError("Registration has closed, so you can't add guests.")
            _check_party_fits_position(new_size, position)
        if (
            new_size < old_size
            and registration.status == Status.REGISTERED
            and now >= cancellation_closes_at(position, site_settings)
        ):
            raise RegistrationError("Cancellation has closed, so you can't remove guests.")
        if registration.status == Status.REGISTERED and new_size > old_size:
            available = available_spots(position)
            if new_size - old_size > available:
                raise RegistrationError(
                    f"Only {available} spot{'s' if available != 1 else ''} left, "
                    "so you can't add that many guests."
                )
        registration.comments = comments
        registration.save(update_fields=["comments", "updated_at"])
        _set_guests(registration, guests)
        if new_size < old_size or registration.status == Status.WAITLISTED:
            _process_waitlist(position, now)
    return registration


# --- Waitlist -------------------------------------------------------------------------------


def process_waitlist(position) -> None:
    with transaction.atomic():
        _process_waitlist(_lock(position), timezone.now())


def cancel(registration) -> None:
    site_settings = SiteSettings.load()
    now = timezone.now()
    with transaction.atomic():
        position = _lock(registration.position)
        registration = _locked_active(registration)
        # The cutoff protects held spots; a waitlist place or an offer can always be given up.
        if registration.status == Status.REGISTERED and now >= cancellation_closes_at(
            position, site_settings
        ):
            raise RegistrationError("Cancellation has closed for this shift.")
        was_registered = registration.status == Status.REGISTERED
        _end(registration, Status.CANCELLED, now)
        if was_registered:
            emails.cancelled(registration)
        _process_waitlist(position, now)


def remove(registration) -> None:
    now = timezone.now()
    with transaction.atomic():
        position = _lock(registration.position)
        registration = _locked_active(registration)
        held_spot = registration.status in HOLDING_STATUSES
        _end(registration, Status.REMOVED, now)
        emails.removed(registration, held_spot=held_spot)
        _process_waitlist(position, now)


def accept_offer(registration) -> None:
    now = timezone.now()
    with transaction.atomic():
        position = _lock(registration.position)
        registration = Registration.objects.select_for_update().get(pk=registration.pk)
        if registration.status != Status.OFFERED:
            raise RegistrationError("This offer is no longer available.")
        if now >= registration.offer_expires_at:
            raise RegistrationError("This offer has expired.")
        if not is_open(position, now):
            raise RegistrationError("Registration isn't open for this position.")
        registration.status = Status.REGISTERED
        registration.save(update_fields=["status", "updated_at"])
        emails.registered(registration)


def decline_offer(registration) -> None:
    now = timezone.now()
    with transaction.atomic():
        position = _lock(registration.position)
        registration = Registration.objects.select_for_update().get(pk=registration.pk)
        if registration.status != Status.OFFERED:
            raise RegistrationError("This offer is no longer available.")
        _end(registration, Status.CANCELLED, now)
        _process_waitlist(position, now)


def promote(registration) -> None:
    """Staff: move a waitlisted party straight in, skipping the offer step."""
    with transaction.atomic():
        position = _lock(registration.position)
        registration = Registration.objects.select_for_update().get(pk=registration.pk)
        if registration.status != Status.WAITLISTED:
            raise RegistrationError("This volunteer is not on the waitlist.")
        if registration.party_size > available_spots(position):
            raise RegistrationError("This party doesn't fit in the open spots.")
        if _overlaps(registration.volunteer, position):
            raise RegistrationError("This volunteer has an overlapping shift.")
        registration.status = Status.REGISTERED
        registration.save(update_fields=["status", "updated_at"])
        emails.registered(registration)


def _locked_active(registration):
    registration = Registration.objects.select_for_update().get(pk=registration.pk)
    if registration.status not in ACTIVE_STATUSES:
        raise RegistrationError("This registration is no longer active.")
    return registration


def _process_waitlist(position, now) -> None:
    """Expire stale offers, then offer (or, close to the start, give) open spots in order."""
    expired = Registration.objects.filter(
        position=position, status=Status.OFFERED, offer_expires_at__lte=now
    ).select_related("volunteer__profile")
    for registration in expired:
        _end(registration, Status.EXPIRED, now)
        emails.offer_expired(registration)
    if not is_open(position, now):
        return
    available = available_spots(position)
    if available <= 0:
        return
    site_settings = SiteSettings.load()
    direct = position.starts_at - now < AUTO_FILL_WINDOW
    expires_at = min(now + timedelta(hours=site_settings.offer_window_hours), position.starts_at)
    waiting = (
        Registration.objects.filter(position=position, status=Status.WAITLISTED)
        .select_related("volunteer")
        .order_by("waitlisted_at", "pk")
    )
    for registration in waiting:
        size = registration.party_size
        if size > available or _overlaps(registration.volunteer, position):
            continue
        if direct:
            registration.status = Status.REGISTERED
            registration.save(update_fields=["status", "updated_at"])
            emails.auto_registered(registration)
        else:
            registration.status = Status.OFFERED
            registration.offered_at = now
            registration.offer_expires_at = expires_at
            registration.save(
                update_fields=["status", "offered_at", "offer_expires_at", "updated_at"]
            )
            emails.offered(registration)
        available -= size
        if available <= 0:
            break


def expire_offers(now=None) -> int:
    """Beat task body: process every position that has an offer past its expiry."""
    now = now or timezone.now()
    position_ids = set(
        Registration.objects.filter(status=Status.OFFERED, offer_expires_at__lte=now).values_list(
            "position_id", flat=True
        )
    )
    for position_id in position_ids:
        with transaction.atomic():
            _process_waitlist(_lock(Position(pk=position_id)), now)
    return len(position_ids)


# --- Attendance -----------------------------------------------------------------------------


def mark_attendance(registration, value, *, by) -> None:
    if value not in Registration.Attendance.values:
        raise RegistrationError("Unknown attendance value.")
    registration = Registration.objects.select_related("position").get(pk=registration.pk)
    if registration.status != Status.REGISTERED:
        raise RegistrationError("Only registered volunteers can be marked.")
    now = timezone.now()
    if now < registration.position.starts_at:
        raise RegistrationError("Attendance can be marked once the shift has started.")
    registration.attendance = value
    registration.attendance_marked_at = now if value else None
    registration.attendance_marked_by = by if value else None
    registration.save(
        update_fields=["attendance", "attendance_marked_at", "attendance_marked_by", "updated_at"]
    )


def mark_all_attended(position, *, by) -> int:
    now = timezone.now()
    if now < position.starts_at:
        raise RegistrationError("Attendance can be marked once the shift has started.")
    return Registration.objects.filter(
        position=position, status=Status.REGISTERED, attendance=""
    ).update(
        attendance=Registration.Attendance.ATTENDED,
        attendance_marked_at=now,
        attendance_marked_by=by,
        updated_at=now,
    )
