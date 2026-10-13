from django.urls import path

from events import manage, views

urlpatterns = [
    path("events/", views.EventListView.as_view(), name="events"),
    path("events/<int:pk>/", views.EventDetailView.as_view(), name="event_detail"),
    path("manage/locations/", manage.LocationListView.as_view(), name="manage_locations"),
    path("manage/locations/new/", manage.LocationCreateView.as_view(), name="manage_location_new"),
    path(
        "manage/locations/<int:pk>/edit/",
        manage.LocationUpdateView.as_view(),
        name="manage_location_edit",
    ),
    path(
        "manage/locations/<int:pk>/delete/",
        manage.LocationDeleteView.as_view(),
        name="manage_location_delete",
    ),
    path("manage/events/", manage.EventListManageView.as_view(), name="manage_events"),
    path("manage/events/new/", manage.EventCreateManageView.as_view(), name="manage_event_new"),
    path(
        "manage/events/archive/",
        manage.EventBulkArchiveView.as_view(),
        name="manage_events_archive",
    ),
    path("manage/events/<int:pk>/", manage.EventHubView.as_view(), name="manage_event"),
    path(
        "manage/events/<int:pk>/edit/",
        manage.EventUpdateManageView.as_view(),
        name="manage_event_edit",
    ),
    path(
        "manage/events/<int:pk>/actions/<slug:action>/",
        manage.EventActionView.as_view(),
        name="manage_event_action",
    ),
    path(
        "manage/events/<int:pk>/positions/new/",
        manage.PositionCreateView.as_view(),
        name="manage_position_new",
    ),
    path(
        "manage/positions/<int:pk>/edit/",
        manage.PositionUpdateView.as_view(),
        name="manage_position_edit",
    ),
    path(
        "manage/positions/<int:pk>/delete/",
        manage.PositionDeleteView.as_view(),
        name="manage_position_delete",
    ),
    path(
        "manage/events/<int:pk>/photos/",
        manage.PhotoUploadView.as_view(),
        name="manage_photos_upload",
    ),
    path(
        "manage/photos/<int:pk>/move/<slug:direction>/",
        manage.PhotoMoveView.as_view(),
        name="manage_photo_move",
    ),
    path(
        "manage/photos/<int:pk>/delete/",
        manage.PhotoDeleteView.as_view(),
        name="manage_photo_delete",
    ),
]
