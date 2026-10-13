from django import forms
from django.db import models

from core.richtext import sanitize_html


class TrixWidget(forms.Widget):
    """Trix editor bound to a hidden input that holds the HTML."""

    template_name = "widgets/trix.html"

    def format_value(self, value):
        return value or ""


class RichTextField(models.TextField):
    """Text field holding sanitized HTML from the Trix editor."""

    def pre_save(self, model_instance, add):
        value = sanitize_html(getattr(model_instance, self.attname))
        setattr(model_instance, self.attname, value)
        return value

    def formfield(self, **kwargs):
        return super().formfield(**{"widget": TrixWidget, **kwargs})
