from django import template
from django.utils import timezone
from django.utils.dateformat import format as date_format

register = template.Library()


@register.filter
def date_range(start, end):
    """'Sat, Nov 7, 2026 · 9:00 AM – 1:00 PM', 'Nov 7 – Nov 8, 2026' or across years."""
    if start is None or end is None:
        return "Dates to be announced"
    start, end = timezone.localtime(start), timezone.localtime(end)
    if start.date() == end.date():
        return (
            f"{date_format(start, 'D, M j, Y')} · "
            f"{date_format(start, 'g:i A')} – {date_format(end, 'g:i A')}"
        )
    if start.year == end.year:
        return f"{date_format(start, 'M j')} – {date_format(end, 'M j, Y')}"
    return f"{date_format(start, 'M j, Y')} – {date_format(end, 'M j, Y')}"


@register.filter
def time_range(start, end):
    """'9:30 AM – 12:00 PM', or '10:00 PM – Sun 2:00 AM' when the end is on a later day."""
    start, end = timezone.localtime(start), timezone.localtime(end)
    end_format = "g:i A" if start.date() == end.date() else "D g:i A"
    return f"{date_format(start, 'g:i A')} – {date_format(end, end_format)}"
