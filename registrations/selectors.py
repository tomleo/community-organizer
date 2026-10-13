from django.db.models import Count, Q
from django.utils import timezone

from registrations import services
from registrations.models import ACTIVE_STATUSES, HOLDING_STATUSES, Registration


def with_capacity(positions):
    holding = Q(registrations__status__in=HOLDING_STATUSES)
    return positions.annotate(
        held_parties=Count("registrations", filter=holding, distinct=True),
        held_guests=Count("registrations__guests", filter=holding, distinct=True),
        waitlist_count=Count(
            "registrations",
            filter=Q(registrations__status=Registration.Status.WAITLISTED),
            distinct=True,
        ),
    )


def attach_visitor_status(user, positions, site_settings, now=None):
    """Annotate positions (already passed through with_capacity) for the event page."""
    now = now or timezone.now()
    positions = list(positions)
    mine = {}
    if user.is_authenticated:
        mine = {
            registration.position_id: registration
            for registration in Registration.objects.filter(
                volunteer=user, position__in=positions, status__in=ACTIVE_STATUSES
            )
        }
    for position in positions:
        position.spots_taken = position.held_parties + position.held_guests
        position.spots_left = max(position.slots - position.spots_taken, 0)
        position.registration_open = services.is_open(position, now) and now < (
            services.registration_closes_at(position, site_settings)
        )
        position.my_registration = mine.get(position.pk)
        position.my_place = None
        if position.my_registration and position.my_registration.status == "waitlisted":
            position.my_place = services.waitlist_place(position.my_registration)
    return positions
