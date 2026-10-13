from django import template

from accounts.questions import yes_labels as _yes_labels

register = template.Library()


@register.filter
def yes_labels(answers, questions):
    return _yes_labels(answers, questions)
