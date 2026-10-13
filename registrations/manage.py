"""Staff roster pages under /manage/."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, TemplateView

from accounts.questions import active_questions, guest_questions, yes_labels
from events.models import Position
from organization.models import SiteSettings
from registrations import services
from registrations.forms import StaffRegistrationForm
from registrations.models import ACTIVE_STATUSES, Registration
from registrations.services import RegistrationError
from volunteers.csv_export import csv_response

Status = Registration.Status


class RosterView(PermissionRequiredMixin, DetailView):
    permission_required = "registrations.view_registration"
    model = Position
    template_name = "manage/positions/roster.html"
    context_object_name = "position"

    def get_queryset(self):
        return Position.objects.select_related("event", "location").prefetch_related(
            Prefetch(
                "registrations",
                queryset=Registration.objects.select_related("volunteer__profile")
                .prefetch_related("guests")
                .order_by("waitlisted_at", "created_at"),
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        registrations = list(self.object.registrations.all())
        taken = services.spots_taken(self.object)
        available = self.object.slots - taken
        waitlist = [r for r in registrations if r.status == Status.WAITLISTED]
        for registration in waitlist:
            registration.fits = len(registration.guests.all()) + 1 <= available
        context.update(
            registered=[r for r in registrations if r.status == Status.REGISTERED],
            offered=[r for r in registrations if r.status == Status.OFFERED],
            waitlist=waitlist,
            taken=taken,
            started=timezone.now() >= self.object.starts_at,
            available=max(available, 0),
            add_form=StaffRegistrationForm(max_guests=SiteSettings.load().max_guests),
            questions=list(active_questions()),
            guest_question_list=list(guest_questions()),
        )
        return context


class RosterAddView(PermissionRequiredMixin, View):
    permission_required = "registrations.change_registration"
    http_method_names = ["post"]

    def post(self, request, pk):
        position = get_object_or_404(Position.objects.select_related("event"), pk=pk)
        form = StaffRegistrationForm(request.POST, max_guests=SiteSettings.load().max_guests)
        if not form.is_valid():
            messages.error(request, "Check the volunteer's email and guest names.")
            return redirect("manage_roster", pk=pk)
        volunteer = (
            get_user_model().objects.filter(email__iexact=form.cleaned_data["email"]).first()
        )
        if volunteer is None:
            messages.error(request, "No volunteer with that email.")
            return redirect("manage_roster", pk=pk)
        try:
            registration = services.register(
                volunteer, position, form.guests(), form.cleaned_data["comments"], by_staff=True
            )
        except RegistrationError as exc:
            messages.error(request, str(exc))
        else:
            where = "the waitlist" if registration.status == Status.WAITLISTED else "this position"
            messages.success(request, f"Added {volunteer.email} to {where}.")
        return redirect("manage_roster", pk=pk)


class RemoveRegistrationView(PermissionRequiredMixin, TemplateView):
    permission_required = "registrations.change_registration"
    template_name = "manage/registrations/remove.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm(self.permission_required):
            return self.handle_no_permission()
        self.registration = get_object_or_404(
            Registration.objects.select_related("volunteer", "position__event"), pk=kwargs["pk"]
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return super().get_context_data(registration=self.registration, **kwargs)

    def post(self, request, *args, **kwargs):
        try:
            services.remove(self.registration)
        except RegistrationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Removed {self.registration.volunteer.email}.")
        return redirect("manage_roster", pk=self.registration.position_id)


class PromoteRegistrationView(PermissionRequiredMixin, View):
    permission_required = "registrations.change_registration"
    http_method_names = ["post"]

    def post(self, request, pk):
        registration = get_object_or_404(Registration.objects.select_related("volunteer"), pk=pk)
        try:
            services.promote(registration)
        except RegistrationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Moved up {registration.volunteer.email}.")
        return redirect("manage_roster", pk=registration.position_id)


class AttendanceView(PermissionRequiredMixin, View):
    permission_required = "registrations.change_registration"
    http_method_names = ["post"]

    def post(self, request, pk):
        registration = get_object_or_404(Registration, pk=pk)
        value = request.POST.get("attendance", "")
        if value and value == registration.attendance:
            value = ""  # pressing the active button again clears the mark
        try:
            services.mark_attendance(registration, value, by=request.user)
        except RegistrationError as exc:
            messages.error(request, str(exc))
        return redirect("manage_roster", pk=registration.position_id)


class MarkAllAttendedView(PermissionRequiredMixin, View):
    permission_required = "registrations.change_registration"
    http_method_names = ["post"]

    def post(self, request, pk):
        position = get_object_or_404(Position, pk=pk)
        try:
            count = services.mark_all_attended(position, by=request.user)
        except RegistrationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Marked {count} as attended.")
        return redirect("manage_roster", pk=pk)


ROSTER_HEADER = [
    "First name",
    "Last name",
    "Email",
    "Phone",
    "Status",
    "Attendance",
    "Guests",
    "Comment",
    "Registered at",
]


def _guest_text(guest, guest_qs) -> str:
    details = [part for part in [guest.relationship, *yes_labels(guest.answers, guest_qs)] if part]
    name = f"{guest.first_name} {guest.last_name}"
    return f"{name} ({'; '.join(details)})" if details else name


class RosterExportView(PermissionRequiredMixin, View):
    permission_required = "registrations.view_registration"

    def get(self, request, pk):
        position = get_object_or_404(Position, pk=pk)
        registrations = (
            position.registrations.filter(status__in=ACTIVE_STATUSES)
            .select_related("volunteer__profile")
            .prefetch_related("guests")
            .order_by("status", "created_at")
        )
        questions = list(active_questions())
        guest_qs = list(guest_questions())
        rows = [
            [
                r.volunteer.profile.first_name,
                r.volunteer.profile.last_name,
                r.volunteer.email,
                r.volunteer.profile.phone,
                r.get_status_display(),
                r.get_attendance_display(),
                "; ".join(_guest_text(g, guest_qs) for g in r.guests.all()),
                r.comments,
                timezone.localtime(r.created_at).strftime("%Y-%m-%d %H:%M"),
                *[
                    "Yes" if (r.volunteer.profile.answers or {}).get(str(q.pk)) else "No"
                    for q in questions
                ],
            ]
            for r in registrations
        ]
        header = ROSTER_HEADER + [q.label for q in questions]
        return csv_response(f"roster-{position.pk}.csv", header, rows)
