"""Logging handlers."""

from django.utils import log


class AdminEmailHandler(log.AdminEmailHandler):
    """Django's error emails, but an unreachable mail server can't turn an error page into a crash.

    With MAILERS configured, Django 6.1's handler lets sending errors escape from logger.error().
    """

    def emit(self, record):
        try:
            super().emit(record)
        except Exception:
            self.handleError(record)  # prints the traceback to stderr
