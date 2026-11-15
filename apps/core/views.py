"""Views that serve the PWA bootstrap files with the headers the spec requires.

The service worker must be served from the root scope (``/sw.js``) so that it can
control every route of the origin, and it must never be served from the HTTP
cache — otherwise a stale worker keeps serving an old shell. The manifest is
likewise served with a revalidation policy.
"""

from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse

PWA_DIR = Path(settings.BASE_DIR) / "static" / "pwa"


def _pwa_file(name: str) -> Path:
    path = PWA_DIR / name
    if not path.exists():  # pragma: no cover - packaging error
        raise Http404(f"PWA asset {name} is missing")
    return path


def service_worker_view(request):
    # Django 6's FileResponse wants a file object, not a path.
    handle = _pwa_file("sw.js").open("rb")
    response = FileResponse(handle, content_type="application/javascript")
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Service-Worker-Allowed"] = "/"
    response["Pragma"] = "no-cache"
    return response


def manifest_view(request):
    handle = _pwa_file("manifest.webmanifest").open("rb")
    response = FileResponse(handle, content_type="application/manifest+json")
    response["Cache-Control"] = "no-cache"
    return response


def offline_fallback(request):  # pragma: no cover - simple redirect helper
    from django.shortcuts import redirect

    return redirect("/offline/")
