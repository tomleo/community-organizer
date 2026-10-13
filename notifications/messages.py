"""One helper per email kind: render and queue. Called inside the triggering transaction."""

from django.urls import reverse

from events.templatetags.event_tags import date_range
from notifications import outbox
from notifications.calendar import shift_ics
from notifications.models import OutgoingEmail
from notifications.render import absolute_url, render_email, site_timezone
from registrations.models import ACTIVE_STATUSES, HOLDING_STATUSES, Registration

Kind = OutgoingEmail.Kind


def _context(registration) -> dict:
    position = registration.position
    event = position.event
    profile = registration.volunteer.profile
    return {
        "registration": registration,
        "position": position,
        "event": event,
        "place": position.effective_location,
        "when": date_range(position.starts_at, position.ends_at),
        "name": profile.first_name or registration.volunteer.email,
        "registration_url": absolute_url(reverse("registration", args=[registration.pk])),
        "event_url": absolute_url(event.get_absolute_url()),
        "profile_url": absolute_url(reverse("profile")),
    }


def _send(kind, registration, *, ics_method=None, ics_bump=None, dedupe_key=None, **extra):
    # Dates like "Sat, Nov 8 · 9:00 AM" are formatted while building the context, so the site
    # time zone must be active here too, not only while the templates render.
    with site_timezone():
        context = {**_context(registration), **extra}
        subject, text, html = render_email(kind, context)
    ics = shift_ics(registration, method=ics_method, sequence_bump=ics_bump) if ics_method else ""
    return outbox.queue(
        kind=kind,
        user=registration.volunteer,
        subject=subject,
        text_body=text,
        html_body=html,
        ics=ics,
        dedupe_key=dedupe_key,
    )


def registered(registration):
    return _send(Kind.REGISTERED, registration, ics_method="PUBLISH")


def waitlisted(registration, place):
    return _send(Kind.WAITLISTED, registration, place=place)


def offered(registration):
    return _send(Kind.OFFERED, registration)


def auto_registered(registration):
    return _send(Kind.AUTO_REGISTERED, registration, ics_method="PUBLISH")


def offer_expired(registration):
    return _send(Kind.OFFER_EXPIRED, registration)


def cancelled(registration):
    return _send(Kind.CANCELLED, registration, ics_method="CANCEL")


def removed(registration, held_spot):
    return _send(Kind.REMOVED, registration, ics_method="CANCEL" if held_spot else None)


def _active_registrations(event):
    return Registration.objects.filter(
        position__event=event, status__in=ACTIVE_STATUSES
    ).select_related("volunteer__profile", "position__event__location", "position__location")


def event_cancelled(event):
    for registration in _active_registrations(event):
        holding = registration.status in HOLDING_STATUSES
        # The caller bumps schedule_version before this, so the CANCEL needs no extra bump and a
        # later reinstatement (another bump) still has a higher SEQUENCE.
        _send(
            Kind.EVENT_CANCELLED,
            registration,
            ics_method="CANCEL" if holding else None,
            ics_bump=0,
        )


def event_reinstated(event):
    for registration in _active_registrations(event):
        holding = registration.status in HOLDING_STATUSES
        _send(Kind.EVENT_REINSTATED, registration, ics_method="PUBLISH" if holding else None)


def position_changed(position, old_when, old_location):
    registrations = position.registrations.filter(status__in=ACTIVE_STATUSES).select_related(
        "volunteer__profile", "position__event__location", "position__location"
    )
    for registration in registrations:
        holding = registration.status in HOLDING_STATUSES
        _send(
            Kind.POSITION_CHANGED,
            registration,
            ics_method="PUBLISH" if holding else None,
            dedupe_key=f"position_changed:{registration.pk}:{position.schedule_version}",
            old_when=old_when,
            old_location=old_location,
        )


def reminder(registration):
    return _send(
        Kind.REMINDER,
        registration,
        ics_method="PUBLISH",
        dedupe_key=f"reminder:{registration.pk}",
    )


def staff_digest(user, digest, date):
    subject, text, html = render_email(
        Kind.STAFF_DIGEST,
        {
            "name": user.profile.first_name or user.email,
            "digest": digest,
            "date": date,
            "manage_url": absolute_url(reverse("manage_events")),
        },
    )
    return outbox.queue(
        kind=Kind.STAFF_DIGEST,
        user=user,
        subject=subject,
        text_body=text,
        html_body=html,
        dedupe_key=f"digest:{user.pk}:{date}",
    )


def group_message(message, user):
    with site_timezone():
        subject, text, html = render_email(
            Kind.MESSAGE,
            {
                "name": user.profile.first_name or user.email,
                "message": message,
                "sender_name": (
                    message.sender.profile.full_name or message.sender.email
                    if message.sender
                    else ""
                ),
            },
        )
    return outbox.queue(
        kind=Kind.MESSAGE,
        user=user,
        subject=subject,
        text_body=text,
        html_body=html,
        reply_to=message.sender.email if message.sender else "",
        message=message,
        dedupe_key=f"message:{message.pk}:{user.pk}",
    )
