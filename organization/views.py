from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from core.tasks import queue_resize
from organization.forms import SiteSettingsForm
from organization.models import ABOUT_IMAGE_SIZES, HOME_IMAGE_SIZES, SiteSettings


class SiteSettingsView(PermissionRequiredMixin, UpdateView):
    permission_required = "organization.change_sitesettings"
    form_class = SiteSettingsForm
    template_name = "organization/site_settings_form.html"
    success_url = reverse_lazy("manage_settings")

    def get_object(self, queryset=None):
        # Read from the database, not the cache, so the form edits the current row.
        site_settings, _ = SiteSettings.objects.get_or_create(pk=1)
        return site_settings

    def get_context_data(self, **kwargs):
        from core.backups import backup_status

        return super().get_context_data(backup_status=backup_status(), **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        if "logo" in form.changed_data:
            queue_resize(self.object.logo)
        if "home_image" in form.changed_data:
            queue_resize(self.object.home_image, HOME_IMAGE_SIZES)
        if "about_image" in form.changed_data:
            queue_resize(self.object.about_image, ABOUT_IMAGE_SIZES)
        messages.success(self.request, "Settings saved.")
        return response
