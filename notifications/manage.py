import uuid
from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import DetailView, ListView

from notifications.group import ROSTER_STATUSES, audience_from_params, create_message
from notifications.models import Message, OutgoingEmail


class EmailLogView(PermissionRequiredMixin, ListView):
    permission_required = "notifications.view_outgoingemail"
    template_name = "manage/emails/list.html"
    context_object_name = "emails"
    paginate_by = 50

    def get_queryset(self):
        emails = OutgoingEmail.objects.all()
        status = self.request.GET.get("status", "")
        if status in OutgoingEmail.Status.values:
            emails = emails.filter(status=status)
        query = self.request.GET.get("q", "").strip()
        if query:
            emails = emails.filter(to__icontains=query)
        return emails

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = {
            key: self.request.GET[key] for key in ("status", "q") if self.request.GET.get(key)
        }
        context.update(
            statuses=OutgoingEmail.Status.choices,
            status=self.request.GET.get("status", ""),
            q=self.request.GET.get("q", ""),
            query=urlencode(params),
        )
        return context


class EmailDetailView(PermissionRequiredMixin, DetailView):
    permission_required = "notifications.view_outgoingemail"
    model = OutgoingEmail
    template_name = "manage/emails/detail.html"
    context_object_name = "email"


class MessageForm(forms.Form):
    subject = forms.CharField(max_length=200)
    body = forms.CharField(widget=forms.Textarea(attrs={"rows": 8}))


def _parse_token(value):
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


class MessageComposeView(PermissionRequiredMixin, View):
    permission_required = "notifications.add_message"

    def _context(self, request, form, audience):
        is_roster = bool(request.GET.get("position") or request.GET.get("event"))
        return {
            "form": form,
            "audience": audience,
            "is_roster": is_roster,
            "statuses": ROSTER_STATUSES,
            "chosen": request.GET.getlist("statuses") or ["registered"],
            "query": request.GET.urlencode(),
        }

    def get(self, request):
        audience = audience_from_params(request.GET)
        return render(
            request, "manage/messages/compose.html", self._context(request, MessageForm(), audience)
        )

    def post(self, request):
        audience = audience_from_params(request.GET)
        form = MessageForm(request.POST)
        context = self._context(request, form, audience)
        if not form.is_valid():
            return render(request, "manage/messages/compose.html", context)
        step = request.POST.get("step")
        if step == "edit":
            return render(request, "manage/messages/compose.html", context)
        if audience is None or not audience.users:
            context["error"] = "Nobody to send to."
            return render(request, "manage/messages/preview.html", context)
        if step != "send":
            context["send_token"] = uuid.uuid4()
            return render(request, "manage/messages/preview.html", context)
        token = _parse_token(request.POST.get("send_token", ""))
        existing = Message.objects.filter(send_token=token).first() if token else None
        if existing:
            return redirect("manage_message", pk=existing.pk)  # already sent: don't send twice
        try:
            with transaction.atomic():
                message = create_message(
                    request.user,
                    form.cleaned_data["subject"],
                    form.cleaned_data["body"],
                    audience,
                    send_token=token,
                )
        except IntegrityError:  # the same token raced in from a second click
            return redirect("manage_message", pk=Message.objects.get(send_token=token).pk)
        count = message.recipient_count
        messages.success(request, f"Sending to {count} volunteer{'s' if count != 1 else ''}.")
        return redirect("manage_message", pk=message.pk)


class MessageListView(PermissionRequiredMixin, ListView):
    permission_required = "notifications.view_message"
    model = Message
    template_name = "manage/messages/list.html"
    context_object_name = "sent"
    paginate_by = 50

    def get_queryset(self):
        return Message.objects.select_related("sender__profile")


class MessageDetailView(PermissionRequiredMixin, DetailView):
    permission_required = "notifications.view_message"
    model = Message
    template_name = "manage/messages/detail.html"
    context_object_name = "sent_message"

    def get_context_data(self, **kwargs):
        return super().get_context_data(emails=self.object.emails.order_by("to"), **kwargs)
