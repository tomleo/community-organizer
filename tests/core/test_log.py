import logging

from core.log import AdminEmailHandler


def test_unreachable_mail_server_does_not_break_error_handling(settings, monkeypatch, capsys):
    settings.ADMINS = ["ops@example.org"]

    def unreachable(*args, **kwargs):
        raise OSError("Name or service not known")

    monkeypatch.setattr("django.core.mail.mail_admins", unreachable)
    record = logging.LogRecord("django.request", logging.ERROR, __file__, 1, "boom", None, None)
    AdminEmailHandler().emit(record)  # must not raise
    assert "Name or service not known" in capsys.readouterr().err
