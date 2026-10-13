from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from accounts.models import Profile


class OnboardingMiddleware:
    """Send signed-in users to onboarding until their profile has every required field."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._needs_onboarding(request):
            onboarding_url = reverse("onboarding")
            if request.method == "GET":
                onboarding_url += "?" + urlencode({"next": request.get_full_path()})
            return redirect(onboarding_url)
        return self.get_response(request)

    def _needs_onboarding(self, request) -> bool:
        user = request.user
        if not user.is_authenticated or self._is_exempt(request.path_info):
            return False
        profile, _ = Profile.objects.get_or_create(user=user)
        return bool(profile.missing_required_fields())

    @staticmethod
    def _is_exempt(path: str) -> bool:
        exempt_prefixes = (
            reverse("onboarding"),
            reverse("account_delete"),  # deleting an account must not require more personal data
            "/accounts/",  # allauth: logout, email verification, password reset
            "/admin/",
            settings.STATIC_URL,
            settings.MEDIA_URL,
        )
        return path.startswith(exempt_prefixes)
