from allauth.account.adapter import DefaultAccountAdapter
from allauth.core import context
from django.contrib.sites.shortcuts import get_current_site

from core.tasks import queue_email
from organization.models import SiteSettings


class AccountAdapter(DefaultAccountAdapter):
    def send_mail(self, template_prefix: str, email: str, context_data: dict) -> None:
        """Render in the request (templates need it), then send from a Celery task."""
        request = context.request
        ctx = {"request": request, "email": email, "current_site": get_current_site(request)}
        ctx.update(context_data)
        message = self.render_mail(template_prefix, email, ctx)
        contact_email = SiteSettings.load().contact_email
        if contact_email:
            message.reply_to = [contact_email]
        queue_email(message)
