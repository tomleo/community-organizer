from django.urls import path

from organization import views

urlpatterns = [
    path("manage/settings/", views.SiteSettingsView.as_view(), name="manage_settings"),
]
