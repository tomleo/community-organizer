from django import forms

from core.images import validate_image_upload
from events.models import EVENT_PHOTO_LIMIT, Event, Location, Position


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = [
            "name",
            "address_line1",
            "address_line2",
            "city",
            "region",
            "postal_code",
            "country",
            "notes",
            "map_url",
            "latitude",
            "longitude",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ["title", "location", "description", "resources_url"]


DATETIME_LOCAL = "%Y-%m-%dT%H:%M"


class PositionForm(forms.ModelForm):
    class Meta:
        model = Position
        fields = ["title", "starts_at", "ends_at", "slots", "location", "description"]
        widgets = {
            "starts_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format=DATETIME_LOCAL
            ),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DATETIME_LOCAL),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].empty_label = "Same as event"

    def clean_slots(self):
        from registrations.services import spots_taken

        slots = self.cleaned_data["slots"]
        if self.instance.pk:
            taken = spots_taken(self.instance)
            if slots < taken:
                raise forms.ValidationError(
                    "%(taken)s people are registered or holding offers, so spots can't be lower.",
                    code="below_taken",
                    params={"taken": taken},
                )
        return slots


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    """Accepts several image files from one input; each is validated like a single upload."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "widget", MultipleFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"})
        )
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else [data]
        cleaned = [super(MultipleImageField, self).clean(file, initial) for file in files if file]
        if not cleaned and self.required:
            raise forms.ValidationError(self.error_messages["required"], code="required")
        for file in cleaned:
            validate_image_upload(file)
        return cleaned


class PhotoUploadForm(forms.Form):
    photos = MultipleImageField(label="Add photos")

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event

    def clean_photos(self):
        photos = self.cleaned_data["photos"]
        remaining = EVENT_PHOTO_LIMIT - self.event.photos.count()
        if len(photos) > remaining:
            raise forms.ValidationError(
                "Events can have at most %(limit)s photos. "
                "You can add %(remaining)s more photo%(s)s.",
                code="too_many_photos",
                params={
                    "limit": EVENT_PHOTO_LIMIT,
                    "remaining": remaining,
                    "s": "" if remaining == 1 else "s",
                },
            )
        return photos
