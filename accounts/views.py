from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import TemplateView, UpdateView

from accounts.forms import ProfileForm
from core.tasks import queue_resize
from registrations import services as registration_services
from registrations.models import Registration
from volunteers.services import VolunteerAdminError, anonymize, volunteer_stats


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        Status = Registration.Status
        mine = Registration.objects.filter(volunteer=self.request.user).select_related(
            "position__event"
        )
        upcoming = list(
            mine.filter(
                status__in=[Status.REGISTERED, Status.WAITLISTED], position__ends_at__gte=now
            ).order_by("position__starts_at")
        )
        for registration in upcoming:
            registration.place = (
                registration_services.waitlist_place(registration)
                if registration.status == Status.WAITLISTED
                else None
            )
        context.update(
            offers=mine.filter(status=Status.OFFERED, position__starts_at__gt=now).order_by(
                "offer_expires_at"
            ),
            upcoming=upcoming,
            past=mine.filter(status=Status.REGISTERED, position__ends_at__lt=now).order_by(
                "-position__starts_at"
            ),
        )
        context["stats"] = volunteer_stats(
            get_user_model().objects.filter(pk=self.request.user.pk)
        ).get()
        return context


class ProfileEditView(LoginRequiredMixin, UpdateView):
    form_class = ProfileForm
    template_name = "accounts/profile_form.html"
    success_url = reverse_lazy("profile")
    success_message = "Your profile has been saved."

    def get_object(self, queryset=None):
        return self.request.user.profile

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def form_valid(self, form):
        response = super().form_valid(form)
        if "photo" in form.changed_data:
            queue_resize(self.object.photo)
        messages.success(self.request, self.success_message)
        return response


class OnboardingView(ProfileEditView):
    template_name = "accounts/onboarding.html"
    success_message = "Thanks! Your profile is complete."

    def get_success_url(self):
        next_url = self.request.GET.get("next", "")
        if url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return next_url
        return reverse("home")


class DeleteAccountView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/delete.html"

    def post(self, request):
        typed = request.POST.get("email", "").strip().lower()
        if typed != request.user.email.lower():
            return self.render_to_response(
                self.get_context_data(error="That doesn't match your email address.")
            )
        try:
            anonymize(request.user)
        except VolunteerAdminError as exc:
            messages.error(request, str(exc))
            return redirect("account_delete")
        logout(request)
        messages.success(request, "Your account has been deleted.")
        return redirect("home")
