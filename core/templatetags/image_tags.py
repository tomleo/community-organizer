from django import template

from core.images import variant_url

register = template.Library()


@register.simple_tag
def resized_url(field_file, size):
    return variant_url(field_file, int(size))
