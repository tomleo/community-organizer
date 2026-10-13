from django import template

register = template.Library()


@register.filter
def hours(value):
    """timedelta → '12.5' (hours, one decimal, no trailing .0)."""
    if not value:
        return "0"
    total = round(value.total_seconds() / 3600, 1)
    return f"{total:g}"


@register.filter
def volunteer_name(user):
    """Display name for staff pages; anonymized accounts show as "Deleted volunteer"."""
    profile = user.profile
    if profile.deleted_at:
        return "Deleted volunteer"
    return profile.full_name or user.email


@register.filter
def contact_email(user):
    """The volunteer's email, or "" for anonymized accounts (their address is a placeholder)."""
    return "" if user.profile.deleted_at else user.email
