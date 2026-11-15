"""Root URL configuration.

Five surfaces:

* ``/landing/`` — public landing page for the platform.
* ``/api/``      — REST API consumed by the PWA and by integrations (ERP, RFID, procurement).
* ``/kitchen/``  — tablet-first kitchen screen used to record post-service actuals.
* ``/console/``  — the administrative console: menus, recipes, attendance, forecast, reports, settings.
* ``/dashboard/``— the reporting surface for mess managers and finance officers.
"""

from django.contrib import admin
from django.urls import include, path

from apps.accounts.views import (
    register,
    register_submit,
    registration_code_issue,
    registration_code_revoke,
    registration_console,
    profile_page,
    password_reset_forgot,
    password_reset_request,
    password_reset_confirm,
    password_reset_complete,
)
from apps.core.views import manifest_view, service_worker_view
from apps.landing.views import landing_index
from apps.reporting.views import dashboard_home

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("accounts/register/", register, name="register"),
    path("accounts/register/submit/", register_submit, name="register-submit"),
    path("accounts/password-reset/", password_reset_forgot, name="password-reset"),
    path("accounts/password-reset/request/", password_reset_request, name="password-reset-request"),
    path(
        "accounts/password-reset/confirm/<str:token>/",
        password_reset_confirm,
        name="password-reset-confirm",
    ),
    path(
        "accounts/password-reset/confirm/<str:token>/complete/",
        password_reset_complete,
        name="password-reset-complete",
    ),
    path("accounts/codes/", registration_console, name="registration-console"),
    path("accounts/codes/issue/", registration_code_issue, name="registration-code-issue"),
    path("accounts/codes/<int:code_id>/revoke/", registration_code_revoke, name="registration-code-revoke"),
    # The profile page a person signs into, as opposed to the profile
    # endpoint the API exposes at /api/accounts/profile/. Two routes with one
    # name would make the last one win in reverse(), so the page has its own.
    path("accounts/profile/", profile_page, name="profile-page"),
    path("api/", include("apps.api.urls")),
    path("api/", include("apps.accounts.urls")),
    path("kitchen/", include("apps.reporting.kitchen_urls")),
    path("console/", include("apps.reporting.console_urls")),
    path("dashboard/", include("apps.reporting.dashboard_urls")),
    path("scan/", include("apps.attendance.scan_urls")),
    # PWA bootstrap. The service worker must be served from the root scope so it
    # can control the whole origin, and must never be cached by the browser.
    path("sw.js", service_worker_view, name="service-worker"),
    path("manifest.webmanifest", manifest_view, name="pwa-manifest"),
    path("landing/", landing_index, name="landing"),
    path("", dashboard_home, name="home"),
]
