from django import forms

from accounts.models import Profile
from accounts.questions import active_questions, answers_from, field_name
from accounts.requirements import required_profile_fields
from organization.models import SiteSettings


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "first_name",
            "last_name",
            "phone",
            "date_of_birth",
            "address_line1",
            "address_line2",
            "city",
            "region",
            "postal_code",
            "country",
            "photo",
            "reminder_emails",
            "announcement_emails",
            "staff_digest",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, site_settings=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        for name in required_profile_fields(site_settings or SiteSettings.load()):
            self.fields[name].required = True
        if user is None or not user.has_perm("registrations.view_registration"):
            del self.fields["staff_digest"]
        self.questions = list(active_questions())
        answers = self.instance.answers or {}
        for question in self.questions:
            self.fields[field_name(question)] = forms.BooleanField(
                label=question.label,
                help_text=question.help_text,
                required=False,
                initial=answers.get(str(question.pk), False),
            )

    def save(self, commit=True):
        # Keep answers to archived questions; replace answers to the questions shown on this form.
        self.instance.answers = {
            **(self.instance.answers or {}),
            **answers_from(self.cleaned_data, self.questions),
        }
        return super().save(commit=commit)
