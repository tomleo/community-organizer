from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core.views import HomeView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("anymail/", include("anymail.urls")),
    path("accounts/", include("allauth.urls")),
    path("", HomeView.as_view(), name="home"),
    path("", include("accounts.urls")),
    path("", include("organization.urls")),
    path("", include("events.urls")),
    path("", include("registrations.urls")),
    path("", include("notifications.urls")),
    path("", include("volunteers.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
