"""Staff pages under /manage/."""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import transaction
from django.db.models import F, Max, Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.images import delete_image
from core.tasks import queue_resize
from events.forms import EventForm, LocationForm, PhotoUploadForm, PositionForm
from events.models import (
    EVENT_PHOTO_LIMIT,
    EVENT_PHOTO_SIZES,
    Event,
    EventPhoto,
    EventStateError,
    Location,
    Position,
)
from events.querysets import STAFF_TABS
from events.templatetags.event_tags import date_range
from notifications import messages as emails
from registrations import services as registration_services
from registrations.selectors import with_capacity


class LocationListView(PermissionRequiredMixin, ListView):
    permission_required = "events.change_location"
    model = Location
    template_name = "manage/locations/list.html"
    context_object_name = "locations"


class LocationCreateView(PermissionRequiredMixin, CreateView):
    permission_required = "events.add_location"
    form_class = LocationForm
    template_name = "manage/locations/form.html"
    success_url = reverse_lazy("manage_locations")

    def form_valid(self, form):
        messages.success(self.request, "Location added.")
        return super().form_valid(form)


class LocationUpdateView(PermissionRequiredMixin, UpdateView):
    permission_required = "events.change_location"
    model = Location
    form_class = LocationForm
    template_name = "manage/locations/form.html"
    success_url = reverse_lazy("manage_locations")

    def form_valid(self, form):
        messages.success(self.request, "Location saved.")
        return super().form_valid(form)


class LocationDeleteView(PermissionRequiredMixin, DeleteView):
    permission_required = "events.delete_location"
    model = Location
    template_name = "manage/locations/confirm_delete.html"
    success_url = reverse_lazy("manage_locations")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["events_using"] = self.object.events_using()
        context["positions_using"] = self.object.positions.select_related("event")
        return context

    def form_valid(self, form):
        if self.object.events_using().exists():
            messages.error(self.request, "This location is still in use and can't be deleted.")
            return self.render_to_response(self.get_context_data())
        messages.success(self.request, "Location deleted.")
        return super().form_valid(form)


class EventListManageView(PermissionRequiredMixin, ListView):
    permission_required = "events.change_event"
    template_name = "manage/events/list.html"
    context_object_name = "events"
    paginate_by = 25

    def tab(self) -> str:
        tab = self.request.GET.get("tab", "upcoming")
        return tab if tab in STAFF_TABS else "upcoming"

    def search(self) -> str:
        return self.request.GET.get("q", "").strip()

    def get_queryset(self):
        events = Event.objects.for_staff(self.tab()).select_related("location")
        if self.search():
            events = events.filter(title__icontains=self.search())
        return events

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = {"tab": self.tab()}
        if self.search():
            params["q"] = self.search()
        context.update(tab=self.tab(), tabs=STAFF_TABS, q=self.search(), query=urlencode(params))
        return context


class EventCreateManageView(PermissionRequiredMixin, CreateView):
    permission_required = "events.add_event"
    form_class = EventForm
    template_name = "manage/events/form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Draft created. Add positions, then publish.")
        return response

    def get_success_url(self):
        return reverse("manage_event", args=[self.object.pk])


class EventUpdateManageView(PermissionRequiredMixin, UpdateView):
    permission_required = "events.change_event"
    model = Event
    form_class = EventForm
    template_name = "manage/events/form.html"

    def form_valid(self, form):
        messages.success(self.request, "Event saved.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("manage_event", args=[self.object.pk])


class EventHubView(PermissionRequiredMixin, DetailView):
    permission_required = "events.change_event"
    template_name = "manage/events/detail.html"
    context_object_name = "event"

    def get_queryset(self):
        return (
            Event.objects.with_dates()
            .with_cover()
            .select_related("location")
            .prefetch_related(
                Prefetch(
                    "positions",
                    queryset=with_capacity(Position.objects.select_related("location")),
                )
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["photo_form"] = PhotoUploadForm(event=self.object)
        context["photo_limit"] = EVENT_PHOTO_LIMIT
        return context


EVENT_ACTIONS = {
    "publish": "Event published.",
    "cancel": "Event cancelled.",
    "reinstate": "Event reinstated.",
    "archive": "Event archived.",
    "restore": "Event restored.",
    "pin": "Event pinned to the home page.",
    "unpin": "Event unpinned.",
}


class EventActionView(PermissionRequiredMixin, View):
    permission_required = "events.change_event"
    http_method_names = ["post"]

    def post(self, request, pk, action):
        if action not in EVENT_ACTIONS:
            raise Http404("Unknown action")
        event = get_object_or_404(Event, pk=pk)
        try:
            getattr(event, action)()
        except EventStateError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, EVENT_ACTIONS[action])
            if action in ("cancel", "reinstate"):
                # Calendar SEQUENCE must keep increasing across cancel → reinstate.
                event.positions.update(schedule_version=F("schedule_version") + 1)
            if action == "cancel":
                emails.event_cancelled(event)
            elif action == "reinstate":
                emails.event_reinstated(event)
            if action in ("reinstate", "restore"):
                for position in event.positions.all():
                    registration_services.process_waitlist(position)
        return redirect("manage_event", pk=event.pk)


class EventBulkArchiveView(PermissionRequiredMixin, View):
    permission_required = "events.change_event"
    http_method_names = ["post"]

    def post(self, request):
        ids = [value for value in request.POST.getlist("ids") if value.isdigit()]
        count = Event.objects.filter(pk__in=ids, archived_at__isnull=True).update(
            archived_at=timezone.now(), updated_at=timezone.now()
        )
        messages.success(request, f"Archived {count} event{'s' if count != 1 else ''}.")
        return redirect("manage_events")


class PositionCreateView(PermissionRequiredMixin, CreateView):
    permission_required = "events.add_position"
    form_class = PositionForm
    template_name = "manage/positions/form.html"

    def dispatch(self, request, *args, **kwargs):
        self.event = get_object_or_404(Event, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = Position(event=self.event)
        return kwargs

    def get_context_data(self, **kwargs):
        return super().get_context_data(event=self.event, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Position added.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("manage_event", args=[self.event.pk])


class PositionUpdateView(PermissionRequiredMixin, UpdateView):
    permission_required = "events.change_position"
    model = Position
    form_class = PositionForm
    template_name = "manage/positions/form.html"

    @staticmethod
    def _schedule_key(position):
        return (
            position.starts_at.replace(second=0, microsecond=0),
            position.ends_at.replace(second=0, microsecond=0),
            position.location_id,
        )

    def get_object(self, queryset=None):
        position = super().get_object(queryset)
        self.original = {
            "key": self._schedule_key(position),
            "when": date_range(position.starts_at, position.ends_at),
            "location": position.effective_location.name,
        }
        return position

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            event=self.object.event,
            registered_count=registration_services.spots_taken(self.object),
            **kwargs,
        )

    def form_valid(self, form):
        schedule_changed = self._schedule_key(form.instance) != self.original["key"]
        if schedule_changed:
            form.instance.schedule_version += 1
        response = super().form_valid(form)
        if schedule_changed:
            emails.position_changed(self.object, self.original["when"], self.original["location"])
        registration_services.process_waitlist(self.object)
        messages.success(self.request, "Position saved.")
        return response

    def get_success_url(self):
        return reverse("manage_event", args=[self.object.event_id])


class PositionDeleteView(PermissionRequiredMixin, DeleteView):
    permission_required = "events.delete_position"
    model = Position
    template_name = "manage/positions/confirm_delete.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm(self.permission_required):
            return self.handle_no_permission()
        position = get_object_or_404(Position.objects.select_related("event"), pk=kwargs["pk"])
        if not position.can_delete:
            messages.error(request, "Positions can't be deleted after the event is published.")
            return redirect("manage_event", pk=position.event_id)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Position deleted.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("manage_event", args=[self.object.event_id])


class PhotoUploadView(PermissionRequiredMixin, View):
    permission_required = "events.add_eventphoto"
    http_method_names = ["post"]

    def post(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        form = PhotoUploadForm(request.POST, request.FILES, event=event)
        if not form.is_valid():
            for error in form.errors.get("photos", []):
                messages.error(request, error)
            return redirect("manage_event", pk=event.pk)
        next_position = (event.photos.aggregate(Max("position"))["position__max"] or -1) + 1
        photos = form.cleaned_data["photos"]
        for offset, image in enumerate(photos):
            photo = EventPhoto.objects.create(
                event=event, image=image, position=next_position + offset
            )
            queue_resize(photo.image, EVENT_PHOTO_SIZES)
        messages.success(request, f"Added {len(photos)} photo{'s' if len(photos) != 1 else ''}.")
        return redirect("manage_event", pk=event.pk)


class PhotoMoveView(PermissionRequiredMixin, View):
    permission_required = "events.change_eventphoto"
    http_method_names = ["post"]

    def post(self, request, pk, direction):
        if direction not in ("up", "down"):
            raise Http404("Unknown direction")
        photo = get_object_or_404(EventPhoto, pk=pk)
        photos = list(photo.event.photos.order_by("position", "id"))
        index = photos.index(photo)
        swap = index - 1 if direction == "up" else index + 1
        if 0 <= swap < len(photos):
            photos[index], photos[swap] = photos[swap], photos[index]
            for position, item in enumerate(photos):
                item.position = position
            EventPhoto.objects.bulk_update(photos, ["position"])
        return redirect("manage_event", pk=photo.event_id)


class PhotoDeleteView(PermissionRequiredMixin, View):
    permission_required = "events.delete_eventphoto"
    http_method_names = ["post"]

    def post(self, request, pk):
        photo = get_object_or_404(EventPhoto, pk=pk)
        name, event_id = photo.image.name, photo.event_id
        photo.delete()
        transaction.on_commit(lambda: delete_image(name, EVENT_PHOTO_SIZES))
        messages.success(request, "Photo deleted.")
        return redirect("manage_event", pk=event_id)
