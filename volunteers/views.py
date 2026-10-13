from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from accounts.questions import active_questions
from notifications.models import OutgoingEmail
from organization.roles import Role, get_role
from registrations.models import ACTIVE_STATUSES, Registration
from volunteers.csv_export import csv_response
from volunteers.queries import SORTS, filtered_volunteers
from volunteers.services import (
    VolunteerAdminError,
    anonymize,
    change_role,
    role_label,
    volunteer_stats,
)
from volunteers.templatetags.volunteer_tags import hours as hours_text


class VolunteerListView(PermissionRequiredMixin, ListView):
    permission_required = "accounts.view_profile"
    template_name = "manage/volunteers/list.html"
    context_object_name = "volunteers"
    paginate_by = 50

    def get_queryset(self):
        return filtered_volunteers(self.request.GET)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for user in context["volunteers"]:
            user.role_label = role_label(user)
        questions = list(active_questions())
        question_keys = [f"q_{question.pk}" for question in questions]
        params = {
            key: self.request.GET[key]
            for key in ("q", "role", "upcoming", "sort", *question_keys)
            if self.request.GET.get(key)
        }
        context.update(
            q=self.request.GET.get("q", ""),
            role=self.request.GET.get("role", ""),
            upcoming=self.request.GET.get("upcoming", ""),
            sort=self.request.GET.get("sort", "name"),
            roles=Role.choices,
            sorts=list(SORTS),
            query=urlencode(params),
            question_filters=[
                (question, self.request.GET.get(f"q_{question.pk}", "")) for question in questions
            ],
        )
        return context


class VolunteerDetailView(PermissionRequiredMixin, DetailView):
    permission_required = "accounts.view_profile"
    template_name = "manage/volunteers/detail.html"
    context_object_name = "person"

    def get_queryset(self):
        return volunteer_stats(
            get_user_model().objects.filter(profile__deleted_at__isnull=True)
        ).select_related("profile")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        person, user, now = self.object, self.request.user, timezone.now()
        registrations = Registration.objects.filter(volunteer=person).select_related(
            "position__event"
        )
        context.update(
            role=get_role(person),
            roles=Role.choices,
            upcoming=registrations.filter(
                status__in=ACTIVE_STATUSES, position__starts_at__gt=now
            ).order_by("position__starts_at"),
            past=registrations.filter(
                status=Registration.Status.REGISTERED, position__starts_at__lte=now
            ).order_by("-position__starts_at"),
            can_change_role=user.has_perm("organization.manage_roles")
            and user.pk != person.pk
            and not person.is_superuser,
            can_delete=user.has_perm("accounts.delete_profile")
            and user.pk != person.pk
            and not person.is_superuser,
            answers=[
                (question.label, (person.profile.answers or {}).get(str(question.pk), False))
                for question in active_questions()
            ],
            recent_emails=OutgoingEmail.objects.filter(user=person)[:10]
            if user.has_perm("notifications.view_outgoingemail")
            else None,
        )
        return context


class VolunteerRoleView(PermissionRequiredMixin, View):
    permission_required = "organization.manage_roles"
    http_method_names = ["post"]

    def post(self, request, pk):
        person = get_object_or_404(get_user_model(), pk=pk, profile__deleted_at__isnull=True)
        role = request.POST.get("role", "")
        if role not in Role.values:
            return HttpResponseBadRequest("Unknown role")
        try:
            change_role(request.user, person, role)
        except VolunteerAdminError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Role changed to {Role(role).label}.")
        return redirect("manage_volunteer", pk=pk)


class VolunteerDeleteView(PermissionRequiredMixin, TemplateView):
    permission_required = "accounts.delete_profile"
    template_name = "manage/volunteers/delete.html"

    def get_context_data(self, **kwargs):
        person = get_object_or_404(
            get_user_model(), pk=self.kwargs["pk"], profile__deleted_at__isnull=True
        )
        return super().get_context_data(person=person, **kwargs)

    def post(self, request, pk):
        person = get_object_or_404(get_user_model(), pk=pk, profile__deleted_at__isnull=True)
        try:
            anonymize(person, actor=request.user)
        except VolunteerAdminError as exc:
            messages.error(request, str(exc))
            return redirect("manage_volunteer", pk=pk)
        messages.success(
            request, "Account deleted. Their past shifts are kept as “Deleted volunteer”."
        )
        return redirect("manage_volunteers")


DIRECTORY_HEADER = [
    "First name",
    "Last name",
    "Email",
    "Phone",
    "Role",
    "Joined",
    "Hours",
    "Shifts attended",
    "No-shows",
    "Last shift",
    "Date of birth",
    "Address line 1",
    "Address line 2",
    "City",
    "Region",
    "Postal code",
    "Country",
]


class VolunteerExportView(PermissionRequiredMixin, View):
    permission_required = "accounts.view_profile"

    def get(self, request):
        questions = list(active_questions())
        rows = []
        for person in filtered_volunteers(request.GET):
            profile = person.profile
            answers = profile.answers or {}
            rows.append(
                [
                    profile.first_name,
                    profile.last_name,
                    person.email,
                    profile.phone,
                    role_label(person),
                    person.date_joined.date(),
                    hours_text(person.hours),
                    person.attended_count,
                    person.no_show_count,
                    person.last_shift_at.date() if person.last_shift_at else "",
                    profile.date_of_birth or "",
                    profile.address_line1,
                    profile.address_line2,
                    profile.city,
                    profile.region,
                    profile.postal_code,
                    profile.country,
                    *["Yes" if answers.get(str(q.pk)) else "No" for q in questions],
                ]
            )
        header = DIRECTORY_HEADER + [q.label for q in questions]
        return csv_response("volunteers.csv", header, rows)
