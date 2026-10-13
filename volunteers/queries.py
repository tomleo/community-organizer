from django.contrib.auth import get_user_model
from django.db.models import Q

from accounts.questions import active_questions
from organization.roles import ROLE_GROUPS, Role
from volunteers.services import volunteer_stats

SORTS = {
    "name": ("profile__last_name", "profile__first_name", "email"),
    "joined": ("-date_joined",),
    "hours": ("-hours", "profile__last_name"),
}


def filtered_volunteers(params):
    users = (
        get_user_model()
        .objects.filter(profile__deleted_at__isnull=True)
        .select_related("profile")
        .prefetch_related("groups")
    )
    ids = [value for value in params.getlist("ids") if value.isdigit()]
    if ids:
        users = users.filter(pk__in=ids)
    query = params.get("q", "").strip()
    if query:
        users = users.filter(
            Q(profile__first_name__icontains=query)
            | Q(profile__last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(profile__phone__icontains=query)
        )
    role = params.get("role", "")
    if role == Role.VOLUNTEER:
        users = users.exclude(groups__name__in=ROLE_GROUPS.values())
    elif role in (Role.COORDINATOR, Role.ADMIN):
        users = users.filter(groups__name=ROLE_GROUPS[role])
    for question in active_questions():
        choice = params.get(f"q_{question.pk}", "")
        said_yes = {"profile__answers__contains": {str(question.pk): True}}
        if choice == "yes":
            users = users.filter(**said_yes)
        elif choice == "no":
            users = users.exclude(**said_yes)  # includes volunteers who never answered
    users = volunteer_stats(users)
    if params.get("upcoming") == "1":
        users = users.filter(has_upcoming=True)
    return users.order_by(*SORTS.get(params.get("sort", "name"), SORTS["name"]))
