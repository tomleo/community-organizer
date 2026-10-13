# Maps each SiteSettings flag to the Profile fields it makes required.
REQUIREMENT_FIELDS = {
    "require_name": ("first_name", "last_name"),
    "require_phone": ("phone",),
    "require_date_of_birth": ("date_of_birth",),
    "require_address": ("address_line1", "city", "region", "postal_code", "country"),
    "require_photo": ("photo",),
}


def required_profile_fields(site_settings) -> list[str]:
    return [
        field
        for flag, fields in REQUIREMENT_FIELDS.items()
        if getattr(site_settings, flag)
        for field in fields
    ]
