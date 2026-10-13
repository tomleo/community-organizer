import re

from django.core.exceptions import ValidationError

_PHONE_CHARACTERS = re.compile(r"^[0-9+().\-\s]+$")


def validate_phone(value):
    digits = sum(character.isdigit() for character in value)
    if not _PHONE_CHARACTERS.match(value) or not 7 <= digits <= 15:
        raise ValidationError("Enter a valid phone number.", code="invalid_phone")
