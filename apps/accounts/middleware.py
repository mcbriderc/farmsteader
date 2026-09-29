from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from .models import Farm


class CurrentFarmMiddleware:
    """Sets request.farm from the session's current_farm_id."""

    # /healthz and /readyz must be here or an unauthenticated probe is redirected
    # to the login page, and a checker that treats a 302 as reachable reports the
    # app healthy while it is completely broken.
    EXEMPT_PATHS = ["/accounts/", "/admin/", "/__debug__/", "/healthz", "/readyz"]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.farm = None

        is_exempt = any(request.path.startswith(p) for p in self.EXEMPT_PATHS)

        if not request.user.is_authenticated:
            if not is_exempt:
                login_url = settings.LOGIN_URL
                return redirect(f"{login_url}?next={request.path}")
            return self.get_response(request)

        farm_id = request.session.get("current_farm_id")
        if farm_id:
            try:
                request.farm = Farm.objects.get(
                    id=farm_id, memberships__user=request.user
                )
            except Farm.DoesNotExist:
                del request.session["current_farm_id"]

        if not request.farm and not is_exempt:
            return redirect(reverse("accounts:farm_select"))

        return self.get_response(request)
