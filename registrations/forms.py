from django import forms

from accounts.questions import answers_from, field_name, guest_questions
from registrations.services import GuestData


class GuestForm(forms.Form):
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    relationship = forms.CharField(max_length=100, required=False)

    def __init__(self, *args, questions=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.questions = list(questions)
        for question in self.questions:
            self.fields[field_name(question)] = forms.BooleanField(
                label=question.label, required=False
            )

    @property
    def question_fields(self):
        return [self[field_name(question)] for question in self.questions]

    def clean(self):
        cleaned = super().clean()
        # A row is a guest only if it has names; ticked questions alone don't count.
        if any(cleaned.get(name) for name in ("first_name", "last_name", "relationship")):
            for name in ("first_name", "last_name"):
                if not cleaned.get(name):
                    self.add_error(name, "This field is required.")
        return cleaned

    def guest(self) -> GuestData | None:
        data = getattr(self, "cleaned_data", {})
        if not data.get("first_name"):
            return None
        return GuestData(
            data["first_name"],
            data["last_name"],
            data.get("relationship", ""),
            answers_from(data, self.questions),
        )


class RegistrationForm(forms.Form):
    comments = forms.CharField(
        label="Anything we should know?",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, max_guests=0, initial_guests=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.guest_formset = None
        if max_guests:
            questions = list(guest_questions())
            initial = []
            for g in initial_guests:
                row = {
                    "first_name": g.first_name,
                    "last_name": g.last_name,
                    "relationship": g.relationship,
                }
                for question in questions:
                    row[field_name(question)] = (g.answers or {}).get(str(question.pk), False)
                initial.append(row)
            formset_class = forms.formset_factory(
                GuestForm, extra=max_guests - len(initial), max_num=max_guests, validate_max=True
            )
            self.guest_formset = formset_class(
                self.data if self.is_bound else None,
                initial=initial,
                prefix="guests",
                form_kwargs={"questions": questions},
            )

    def is_valid(self):
        form_valid = super().is_valid()
        formset_valid = self.guest_formset is None or self.guest_formset.is_valid()
        return form_valid and formset_valid

    def guests(self) -> list[GuestData] | None:
        """The submitted guests, or None when guests are turned off (leave existing ones alone)."""
        if self.guest_formset is None:
            return None
        return [guest for form in self.guest_formset.forms if (guest := form.guest())]


class StaffRegistrationForm(RegistrationForm):
    email = forms.EmailField(label="Volunteer's email")

    field_order = ["email", "comments"]
