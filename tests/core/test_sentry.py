from core.sentry import init_sentry


def test_off_without_dsn(monkeypatch):
    calls = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kwargs: calls.append(kwargs))
    assert (
        init_sentry("", release="1.2.0", environment="production", traces_sample_rate=0.0) is False
    )
    assert calls == []


def test_on_with_dsn(monkeypatch):
    calls = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kwargs: calls.append(kwargs))
    assert init_sentry(
        "https://key@sentry.example.org/1",
        release="1.2.0",
        environment="staging",
        traces_sample_rate=0.1,
    )
    (kwargs,) = calls
    assert kwargs["send_default_pii"] is False
    assert kwargs["release"] == "1.2.0"
    assert kwargs["environment"] == "staging"
    assert kwargs["traces_sample_rate"] == 0.1
    assert {type(i).__name__ for i in kwargs["integrations"]} == {
        "DjangoIntegration",
        "CeleryIntegration",
    }
