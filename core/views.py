from django.views.generic import TemplateView

from events.models import Event


class HomeView(TemplateView):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["featured_events"] = (
            Event.objects.with_cover().select_related("location").featured()
        )
        return context
