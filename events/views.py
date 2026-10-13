from itertools import groupby

from django.db.models import Prefetch
from django.utils import timezone
from django.views.generic import DetailView, ListView

from events.jsonld import event_data, jsonld_script
from events.models import Event, Position
from organization.models import SiteSettings
from registrations.selectors import attach_visitor_status, with_capacity


class EventListView(ListView):
    template_name = "events/event_list.html"
    context_object_name = "events"
    paginate_by = 12

    def showing_past(self) -> bool:
        return self.request.GET.get("when") == "past"

    def get_queryset(self):
        events = Event.objects.public().with_cover().select_related("location")
        return events.past() if self.showing_past() else events.upcoming()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["when"] = "past" if self.showing_past() else "upcoming"
        context["query"] = "when=past" if self.showing_past() else ""
        return context


class EventDetailView(DetailView):
    template_name = "events/event_detail.html"
    context_object_name = "event"

    def get_queryset(self):
        events = (
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
        if self.request.user.has_perm("events.change_event"):
            return events
        return events.public()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = self.object
        site_settings = SiteSettings.load()
        positions = attach_visitor_status(self.request.user, event.positions.all(), site_settings)
        context["position_days"] = [
            (day, list(group))
            for day, group in groupby(
                positions, key=lambda position: timezone.localtime(position.starts_at).date()
            )
        ]
        context["can_edit"] = self.request.user.has_perm("events.change_event")
        context["jsonld"] = (
            jsonld_script(event_data(event, self.request, site_settings)) if event.is_public else ""
        )
        return context
