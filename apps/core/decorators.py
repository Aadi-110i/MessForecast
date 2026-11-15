"""A view decorator for surfaces that need a capability.

The API viewsets declare the capability they need and the REST framework
checks it. The plain Django views - the rendered console, the tablet
screens, the capture screen - had no equivalent, so a surface that was not
guarded meant "any signed-in user", which no role in the capability table
actually holds.

This decorator closes that gap. It calls the same ``has_capability`` the
rest of the application uses, so a role change stays a single edit, and it
answers 403 whether the request asked for HTML or for JSON.
"""

from __future__ import annotations

from functools import wraps

from django.http import JsonResponse

from apps.accounts.permissions import has_capability


def requires(*capabilities: str):
    """Allow the request only when the user holds one of ``capabilities``.

    Usage::

        @requires("VIEW_WASTE_COST")
        def dashboard_waste(request):
            ...

    More than one capability means "any of them", which is how a surface
    that two kinds of role legitimately read is written.
    """

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not any(has_capability(request.user, cap) for cap in capabilities):
                return JsonResponse({"detail": "Not permitted"}, status=403)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
