"""Optional error reporting to Sentry (or a compatible service such as GlitchTip)."""


def init_sentry(dsn: str, *, release: str, environment: str, traces_sample_rate: float) -> bool:
    if not dsn:
        return False
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=dsn,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        send_default_pii=False,  # volunteer data is personal
        release=release,
        environment=environment,
        traces_sample_rate=traces_sample_rate,
    )
    return True
