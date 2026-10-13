"""schema.org JSON-LD for public event pages."""

import json

from django.utils import timezone
from django.utils.safestring import mark_safe

from core.images import variant_url
from core.richtext import plain_text

SCHEMA = "https://schema.org/"
_STATUS = {"published": "EventScheduled", "cancelled": "EventCancelled"}
# Same escaping as Django's json_script, so content can't close the <script> element.
_ESCAPES = {ord("<"): "\\u003C", ord(">"): "\\u003E", ord("&"): "\\u0026"}


def _iso(value):
    return timezone.localtime(value).isoformat()


def place(location) -> dict:
    address = {
        "@type": "PostalAddress",
        "streetAddress": location.address_line1,
        "addressLocality": location.city,
        "addressRegion": location.region,
        "postalCode": location.postal_code,
        "addressCountry": location.country,
    }
    if location.address_line2:
        address["extendedAddress"] = location.address_line2
    data = {"@type": "Place", "name": location.name, "address": address}
    if location.latitude is not None and location.longitude is not None:
        data["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": float(location.latitude),
            "longitude": float(location.longitude),
        }
    if location.map_url:
        data["hasMap"] = location.map_url
    return data


def event_data(event, request, site_settings) -> dict:
    status = SCHEMA + _STATUS.get(event.status, "EventScheduled")
    mode = SCHEMA + "OfflineEventAttendanceMode"
    positions = list(event.positions.all())
    organizer = {"@type": "Organization", "name": site_settings.org_name}
    if site_settings.website_url:
        organizer["url"] = site_settings.website_url
    data = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": event.title,
        "description": plain_text(event.description),
        "eventStatus": status,
        "eventAttendanceMode": mode,
        "url": request.build_absolute_uri(event.get_absolute_url()),
        "location": place(event.location),
        "organizer": organizer,
        "subEvent": [
            {
                "@type": "Event",
                "name": position.title,
                "startDate": _iso(position.starts_at),
                "endDate": _iso(position.ends_at),
                "eventStatus": status,
                "eventAttendanceMode": mode,
                "location": place(position.effective_location),
                "maximumAttendeeCapacity": position.slots,
            }
            for position in positions
        ],
    }
    if positions:
        data["startDate"] = _iso(min(position.starts_at for position in positions))
        data["endDate"] = _iso(max(position.ends_at for position in positions))
    images = [
        request.build_absolute_uri(variant_url(photo.image, 1600)) for photo in event.photos.all()
    ]
    if images:
        data["image"] = images
    return data


def jsonld_script(data: dict):
    payload = json.dumps(data).translate(_ESCAPES)
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')
