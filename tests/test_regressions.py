"""Regression tests for the 500s found by ``scripts/sweep_urls.py``.

Each test here corresponds to a route that returned a server error at some
point during the build:

* the dashboard overview called the demand helpers on the reporting module,
* the savings analytics endpoint indexed straight into the query string,
* the capture screen's live-count endpoint used a DRF-only request attribute.

The point of these tests is that a client mistake - a missing date, a mistyped
date, a missing service id - must come back as a 4xx, never as a 500.
"""

from __future__ import annotations

import datetime as dt

from django.test import Client, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User

from .factories import make_hall, make_service, make_user


class DashboardRenderTests(TestCase):
    """The HTML surfaces must render for a signed-in mess manager."""

    def setUp(self):
        self.manager = make_user("manager", User.Role.MESS_MANAGER)
        self.hall = make_hall()
        self.service = make_service(self.hall, dt.date(2026, 11, 5), attendance=480)
        self.client.force_login(self.manager)

    def test_the_overview_page_renders(self):
        response = self.client.get(reverse("dashboard-home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Overview")
        # The rail is capability-aware: a mess manager sees the destinations
        # its role permits (Reports), not the master-data tooling.
        self.assertContains(response, "Reports")

    def test_the_overview_page_renders_with_a_hall_filter(self):
        response = self.client.get(reverse("dashboard-home"), {"hall": self.hall.pk})
        self.assertEqual(response.status_code, 200)

    def test_every_dashboard_page_renders(self):
        for name in (
            "dashboard-waste",
            "dashboard-accuracy",
            "dashboard-planning",
            "dashboard-data-quality",
        ):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)

    def test_a_mistyped_date_in_the_query_string_does_not_crash_the_page(self):
        response = self.client.get(reverse("dashboard-home"), {"start": "not-a-date"})
        self.assertEqual(response.status_code, 200)


class ConsoleScreenTests(TestCase):
    """Every Phase 2 console screen must render for a mess manager.

    These routes are new in Phase 2, so nothing else in the suite covers
    them. A screen that raises is the failure this guards against.
    """

    def setUp(self):
        self.manager = make_user("manager", User.Role.MESS_MANAGER)
        self.client.force_login(self.manager)

    def test_every_console_screen_renders(self):
        for name in (
            "console-menus",
            "console-recipes",
            "console-attendance",
            "console-forecast",
            "console-reports",
            "console-settings",
            "design-system",
        ):
            with self.subTest(screen=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)

    def test_the_registration_code_console_renders_for_an_administrator(self):
        admin = make_user("sysadmin", User.Role.ADMINISTRATOR)
        self.client.force_login(admin)
        response = self.client.get(reverse("registration-console"))
        self.assertEqual(response.status_code, 200)

    def test_the_registration_code_console_is_closed_to_a_mess_manager(self):
        # Codes carry the role a new account gets, so only the mess office
        # may issue one.
        response = self.client.get(reverse("registration-console"))
        self.assertEqual(response.status_code, 403)


class KitchenScreenTests(TestCase):
    """The tablet screens must render for kitchen staff."""

    def setUp(self):
        self.hall = make_hall()
        self.service = make_service(self.hall, dt.date(2026, 11, 5), attendance=480)
        self.kitchen = make_user("chef", User.Role.KITCHEN_STAFF)
        self.kitchen.hall = self.hall
        self.kitchen.save()
        self.client.force_login(self.kitchen)

    def test_the_kitchen_dashboard_renders(self):
        response = self.client.get(reverse("kitchen-dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_the_kitchen_actuals_screen_renders(self):
        response = self.client.get(reverse("kitchen-actuals", args=[self.service.pk]))
        self.assertEqual(response.status_code, 200)


class RegistrationTests(TestCase):
    """An account is made against a code, never by picking a role."""

    def setUp(self):
        self.client = Client()

    def test_the_register_screen_renders_signed_out(self):
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Code from the mess office")

    def test_registering_without_a_code_is_a_400(self):
        response = self.client.post(
            reverse("register-submit"),
            {"username": "newbie", "password": "pass1234", "password_confirm": "pass1234"},
        )
        self.assertEqual(response.status_code, 400)

    def test_a_short_password_is_a_400(self):
        response = self.client.post(
            reverse("register-submit"),
            {"code": "ABCD-1234", "username": "newbie", "password": "short", "password_confirm": "short"},
        )
        self.assertEqual(response.status_code, 400)


class LoginRedirectTests(TestCase):
    """A successful sign-in must land on a page that exists."""

    def test_sign_in_redirects_to_the_dashboard(self):
        self.make_user("manager", User.Role.MESS_MANAGER)
        response = self.client.post(
            reverse("login"),
            {"username": "manager", "password": "pass1234"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/dashboard/")

    def test_the_redirect_target_actually_resolves(self):
        response = self.client.get("/dashboard/")
        self.assertNotEqual(response.status_code, 404)

    @staticmethod
    def make_user(username, role):
        return make_user(username, role)


class SavingsAnalyticsTests(TestCase):
    """``/api/analytics/savings`` needs four dates; missing ones are a 400."""

    def setUp(self):
        self.client = APIClient()
        self.manager = make_user("manager", User.Role.MESS_MANAGER)
        self.client.force_authenticate(self.manager)

    def test_missing_dates_return_400_not_500(self):
        response = self.client.get("/api/analytics/savings")
        self.assertEqual(response.status_code, 400)

    def test_a_mistyped_date_returns_400_not_500(self):
        response = self.client.get(
            "/api/analytics/savings",
            {
                "baseline_start": "yesterday",
                "baseline_end": "2026-01-31",
                "live_start": "2026-02-01",
                "live_end": "2026-02-28",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_a_complete_request_returns_200(self):
        response = self.client.get(
            "/api/analytics/savings",
            {
                "baseline_start": "2026-01-01",
                "baseline_end": "2026-01-28",
                "live_start": "2026-02-01",
                "live_end": "2026-02-28",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("comparison", response.data)


class MalformedDateParameterTests(TestCase):
    """A bad date on any analytics endpoint must be a 400, not a 500."""

    def setUp(self):
        self.client = APIClient()
        self.manager = make_user("manager", User.Role.MESS_MANAGER)
        self.client.force_authenticate(self.manager)

    def test_waste_analytics_rejects_a_mistyped_date(self):
        response = self.client.get("/api/analytics/waste", {"start": "13/11/2026"})
        self.assertEqual(response.status_code, 400)

    def test_demand_analytics_rejects_a_mistyped_date(self):
        response = self.client.get("/api/analytics/demand", {"end": "tomorrow"})
        self.assertEqual(response.status_code, 400)

    def test_forecast_generation_rejects_a_mistyped_date(self):
        response = self.client.post(
            "/api/forecasts/generate/",
            {"start": "not-a-date"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class ScanCountTests(TestCase):
    """The live-count endpoint is a plain Django view, not a DRF view."""

    def setUp(self):
        self.hall = make_hall()
        self.service = make_service(self.hall, dt.date(2026, 11, 5), attendance=480)
        self.kitchen = make_user("chef", User.Role.KITCHEN_STAFF)
        self.kitchen.hall = self.hall
        self.kitchen.save()
        self.client.force_login(self.kitchen)

    def test_the_live_count_is_returned(self):
        response = self.client.get(reverse("scan-count"), {"service": self.service.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["attendance_count"], 480)

    def test_a_missing_service_id_is_a_400(self):
        response = self.client.get(reverse("scan-count"))
        self.assertEqual(response.status_code, 400)
