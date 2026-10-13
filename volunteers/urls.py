from django.urls import path

from volunteers import views

urlpatterns = [
    path("manage/volunteers/", views.VolunteerListView.as_view(), name="manage_volunteers"),
    path(
        "manage/volunteers/export.csv",
        views.VolunteerExportView.as_view(),
        name="manage_volunteers_export",
    ),
    path(
        "manage/volunteers/<int:pk>/", views.VolunteerDetailView.as_view(), name="manage_volunteer"
    ),
    path(
        "manage/volunteers/<int:pk>/role/",
        views.VolunteerRoleView.as_view(),
        name="manage_volunteer_role",
    ),
    path(
        "manage/volunteers/<int:pk>/delete/",
        views.VolunteerDeleteView.as_view(),
        name="manage_volunteer_delete",
    ),
]
