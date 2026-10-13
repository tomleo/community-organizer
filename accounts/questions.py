"""Organization-defined yes/no questions; answers are {"<question id>": bool} maps."""

from accounts.models import ProfileQuestion


def active_questions():
    return ProfileQuestion.objects.filter(archived_at__isnull=True).order_by("order", "id")


def guest_questions():
    return active_questions().filter(ask_guests=True)


def field_name(question) -> str:
    return f"question_{question.pk}"


def answers_from(cleaned_data, questions) -> dict:
    """Answers for `questions` from form data; an unticked box is False."""
    return {
        str(question.pk): bool(cleaned_data.get(field_name(question))) for question in questions
    }


def yes_labels(answers, questions) -> list[str]:
    answers = answers or {}
    return [question.label for question in questions if answers.get(str(question.pk)) is True]
