from django import template
from django.utils.safestring import mark_safe
from django.utils.text import Truncator

from core.richtext import plain_text, sanitize_html

register = template.Library()


@register.filter
def rich_text(value):
    # Sanitized again on output, in case something was written without RichTextField.pre_save.
    return mark_safe(sanitize_html(value))


@register.filter
def excerpt(value, length=160):
    return Truncator(plain_text(value)).chars(int(length))
