"""Staff pages for profile questions."""

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Max
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from accounts.models import ProfileQuestion
from accounts.questions import active_questions


class QuestionForm(forms.ModelForm):
    class Meta:
        model = ProfileQuestion
        fields = ["label", "help_text", "ask_guests"]


class QuestionListView(PermissionRequiredMixin, ListView):
    permission_required = "accounts.change_profilequestion"
    template_name = "manage/questions/list.html"
    context_object_name = "questions"

    def get_queryset(self):
        return active_questions()

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            archived=ProfileQuestion.objects.filter(archived_at__isnull=False), **kwargs
        )


class QuestionCreateView(PermissionRequiredMixin, CreateView):
    permission_required = "accounts.add_profilequestion"
    form_class = QuestionForm
    template_name = "manage/questions/form.html"
    success_url = reverse_lazy("manage_questions")

    def form_valid(self, form):
        highest = ProfileQuestion.objects.aggregate(Max("order"))["order__max"]
        form.instance.order = 0 if highest is None else highest + 1
        messages.success(self.request, "Question added.")
        return super().form_valid(form)


class QuestionUpdateView(PermissionRequiredMixin, UpdateView):
    permission_required = "accounts.change_profilequestion"
    model = ProfileQuestion
    form_class = QuestionForm
    template_name = "manage/questions/form.html"
    success_url = reverse_lazy("manage_questions")

    def form_valid(self, form):
        messages.success(self.request, "Question saved.")
        return super().form_valid(form)


class QuestionMoveView(PermissionRequiredMixin, View):
    permission_required = "accounts.change_profilequestion"
    http_method_names = ["post"]

    def post(self, request, pk, direction):
        if direction not in ("up", "down"):
            raise Http404
        questions = list(active_questions())
        question = get_object_or_404(ProfileQuestion, pk=pk, archived_at__isnull=True)
        index = questions.index(question)
        swap = index - 1 if direction == "up" else index + 1
        if 0 <= swap < len(questions):
            questions[index], questions[swap] = questions[swap], questions[index]
            for order, item in enumerate(questions):
                item.order = order
            ProfileQuestion.objects.bulk_update(questions, ["order"])
        return redirect("manage_questions")


class QuestionArchiveView(PermissionRequiredMixin, View):
    permission_required = "accounts.change_profilequestion"
    http_method_names = ["post"]
    archive = True

    def post(self, request, pk):
        question = get_object_or_404(ProfileQuestion, pk=pk)
        question.archived_at = timezone.now() if self.archive else None
        question.save(update_fields=["archived_at"])
        messages.success(request, "Question archived." if self.archive else "Question restored.")
        return redirect("manage_questions")
