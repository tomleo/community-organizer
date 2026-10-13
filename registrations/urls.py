from django.urls import path

from registrations import manage, views

urlpatterns = [
    path("positions/<int:pk>/register/", views.RegisterView.as_view(), name="register"),
    path("registrations/<int:pk>/", views.ManageRegistrationView.as_view(), name="registration"),
    path(
        "registrations/<int:pk>/cancel/",
        views.CancelRegistrationView.as_view(),
        name="registration_cancel",
    ),
    path(
        "registrations/<int:pk>/accept/",
        views.OfferResponseView.as_view(action="accept"),
        name="registration_accept",
    ),
    path(
        "registrations/<int:pk>/decline/",
        views.OfferResponseView.as_view(action="decline"),
        name="registration_decline",
    ),
    path("manage/positions/<int:pk>/roster/", manage.RosterView.as_view(), name="manage_roster"),
    path(
        "manage/positions/<int:pk>/roster/add/",
        manage.RosterAddView.as_view(),
        name="manage_roster_add",
    ),
    path(
        "manage/registrations/<int:pk>/remove/",
        manage.RemoveRegistrationView.as_view(),
        name="manage_registration_remove",
    ),
    path(
        "manage/registrations/<int:pk>/promote/",
        manage.PromoteRegistrationView.as_view(),
        name="manage_registration_promote",
    ),
    path(
        "manage/registrations/<int:pk>/attendance/",
        manage.AttendanceView.as_view(),
        name="manage_attendance",
    ),
    path(
        "manage/positions/<int:pk>/roster/attended/",
        manage.MarkAllAttendedView.as_view(),
        name="manage_mark_all_attended",
    ),
    path(
        "manage/positions/<int:pk>/roster.csv",
        manage.RosterExportView.as_view(),
        name="manage_roster_export",
    ),
]
