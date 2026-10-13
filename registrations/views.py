from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import FormView, TemplateView

from events.models import Event, Position
from organization.models import SiteSettings
from registrations import services
from registrations.forms import RegistrationForm
from registrations.models import ACTIVE_STATUSES, Registration
from registrations.services import RegistrationError


def outcome_message(registration) -> str:
    if registration.status == Registration.Status.WAITLISTED:
        return f"You're #{services.waitlist_place(registration)} on the waitlist."
    return "You're registered!"


class RegisterView(LoginRequiredMixin, FormView):
    template_name = "registrations/register.html"
    form_class = RegistrationForm

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.position = get_object_or_404(
            Position.objects.filter(event__in=Event.objects.public()).select_related(
                "event__location", "location"
            ),
            pk=kwargs["pk"],
        )

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "max_guests": SiteSettings.load().max_guests}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        available = services.available_spots(self.position)
        waiting = self.position.registrations.filter(status=Registration.Status.WAITLISTED)
        context.update(
            position=self.position,
            event=self.position.event,
            available=available,
            next_waitlist_place=waiting.count() + 1,
        )
        return context

    def form_valid(self, form):
        try:
            registration = services.register(
                self.request.user,
                self.position,
                form.guests(),
                form.cleaned_data["comments"],
            )
        except RegistrationError as exc:
            messages.error(self.request, str(exc))
            return redirect(self.position.event.get_absolute_url())
        messages.success(self.request, outcome_message(registration))
        return redirect(self.position.event.get_absolute_url())


class OwnRegistrationMixin(LoginRequiredMixin):
    """Loads the registration in the URL; 404 unless it belongs to the logged-in volunteer."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.registration = get_object_or_404(
            Registration.objects.select_related("position__event__location", "position__location"),
            pk=kwargs["pk"],
            volunteer=request.user,
        )
        return super().dispatch(request, *args, **kwargs)


class ManageRegistrationView(OwnRegistrationMixin, FormView):
    template_name = "registrations/manage.html"
    form_class = RegistrationForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(
            max_guests=SiteSettings.load().max_guests,
            initial_guests=list(self.registration.guests.all()),
            initial={"comments": self.registration.comments},
        )
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        registration = self.registration
        context.update(
            registration=registration,
            position=registration.position,
            event=registration.position.event,
            editable=registration.status
            in (Registration.Status.REGISTERED, Registration.Status.WAITLISTED)
            and timezone.now() < registration.position.starts_at,
            waitlist_place=services.waitlist_place(registration)
            if registration.status == Registration.Status.WAITLISTED
            else None,
        )
        return context

    def form_valid(self, form):
        try:
            services.update(self.registration, form.guests(), form.cleaned_data["comments"])
        except RegistrationError as exc:
            messages.error(self.request, str(exc))
        else:
            messages.success(self.request, "Your registration has been updated.")
        return redirect("registration", pk=self.registration.pk)


class CancelRegistrationView(OwnRegistrationMixin, TemplateView):
    template_name = "registrations/cancel.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        position = self.registration.position
        context.update(
            registration=self.registration,
            position=position,
            event=position.event,
            cancellation_open=self.registration.status in ACTIVE_STATUSES
            and (
                self.registration.status != Registration.Status.REGISTERED
                or timezone.now() < services.cancellation_closes_at(position, SiteSettings.load())
            ),
        )
        return context

    def post(self, request, *args, **kwargs):
        try:
            services.cancel(self.registration)
        except RegistrationError as exc:
            messages.error(request, str(exc))
            return redirect("registration_cancel", pk=self.registration.pk)
        messages.success(request, "Your registration has been cancelled.")
        return redirect(self.registration.position.event.get_absolute_url())


class OfferResponseView(OwnRegistrationMixin, View):
    http_method_names = ["post"]
    action = None  # "accept" or "decline"

    def post(self, request, *args, **kwargs):
        try:
            if self.action == "accept":
                services.accept_offer(self.registration)
                messages.success(request, "You're registered!")
            else:
                services.decline_offer(self.registration)
                messages.info(request, "You've declined the spot.")
        except RegistrationError as exc:
            messages.error(request, str(exc))
        next_url = request.POST.get("next", "")
        if url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return redirect(next_url)
        return redirect(reverse("profile"))
