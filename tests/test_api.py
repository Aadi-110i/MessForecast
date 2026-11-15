"""The REST API, and the role permissions that guard it."""

from __future__ import annotations

import datetime as dt
import uuid as uuid_lib
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord
from apps.forecasting.models import Forecast

from .factories import (
    add_dish_to_menu,
    make_dish,
    make_hall,
    make_ingredient,
    make_menu,
    make_recipe,
    make_service,
    make_user,
    schedule_menu,
)


class APITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.hall = make_hall()
        self.manager = make_user("manager", User.Role.MESS_MANAGER)
        self.kitchen = make_user("chef", User.Role.KITCHEN_STAFF)
        self.kitchen.hall = self.hall
        self.kitchen.save()
        self.finance = make_user("finance", User.Role.FINANCE_OFFICER)
        self.student = make_user("student", User.Role.STUDENT)
        self.on_date = dt.date(2026, 11, 5)
        self.service = make_service(self.hall, self.on_date, attendance=480)


class AuthenticationTests(APITestCase):
    def test_anonymous_access_is_refused(self):
        response = self.client.get("/api/services/")
        # JWT authentication advertises a Bearer challenge, so an unauthenticated
        # API request is refused with 401 rather than 403.
        self.assertEqual(response.status_code, 401)

    def test_an_authenticated_user_can_read_services(self):
        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/services/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)


class PermissionTests(APITestCase):
    def test_a_student_cannot_read_the_waste_report(self):
        self.client.force_authenticate(self.student)
        response = self.client.get("/api/analytics/waste")
        self.assertEqual(response.status_code, 403)

    def test_a_finance_officer_can_read_the_waste_report(self):
        self.client.force_authenticate(self.finance)
        response = self.client.get("/api/analytics/waste")
        self.assertEqual(response.status_code, 200)
        self.assertIn("totals", response.data)

    def test_a_finance_officer_cannot_change_a_dish(self):
        self.client.force_authenticate(self.finance)
        response = self.client.post("/api/dishes/", {"name": "X", "code": "X"})
        self.assertEqual(response.status_code, 403)

    def test_a_mess_administrator_can_create_a_dish(self):
        admin = make_user("madmin", User.Role.MESS_ADMIN)
        self.client.force_authenticate(admin)
        response = self.client.post(
            "/api/dishes/", {"name": "Khichdi", "code": "KHICHDI2", "serving_size_g": "250"}
        )
        self.assertEqual(response.status_code, 201)

    def test_kitchen_staff_can_record_attendance(self):
        self.client.force_authenticate(self.kitchen)
        payload = {
            "records": [
                {
                    "client_uuid": str(uuid_lib.uuid4()),
                    "service_id": self.service.id,
                    "student_identifier": "2023CS0001",
                    "method": "QR",
                }
            ]
        }
        response = self.client.post("/api/attendance/sync", payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["created"], 1)

    def test_a_student_cannot_sync_attendance(self):
        self.client.force_authenticate(self.student)
        response = self.client.post(
            "/api/attendance/sync", {"records": []}, format="json"
        )
        self.assertEqual(response.status_code, 403)


class SyncEndpointTests(APITestCase):
    def test_the_sync_endpoint_is_idempotent(self):
        self.client.force_authenticate(self.kitchen)
        client_uuid = str(uuid_lib.uuid4())
        payload = {
            "records": [
                {
                    "client_uuid": client_uuid,
                    "service_id": self.service.id,
                    "student_identifier": "2023CS4242",
                    "method": "QR",
                    "captured_offline": True,
                }
            ],
            "device_id": "tablet-01",
        }

        first = self.client.post("/api/attendance/sync", payload, format="json")
        second = self.client.post("/api/attendance/sync", payload, format="json")

        self.assertEqual(first.data["created"], 1)
        self.assertEqual(second.data["created"], 0)
        self.assertEqual(second.data["duplicates"], 1)
        self.assertEqual(AttendanceRecord.objects.count(), 1)


class ForecastEndpointTests(APITestCase):
    def test_forecasts_can_be_generated_and_read(self):
        start = dt.date(2026, 9, 1)
        for index in range(8 * 7):
            current = start + dt.timedelta(days=index)
            make_service(self.hall, current, attendance=500)

        target = dt.date(2026, 10, 27)
        service = make_service(self.hall, target, attendance=540)

        self.client.force_authenticate(self.manager)
        response = self.client.post(
            "/api/forecasts/generate/",
            {"start": target.isoformat(), "end": target.isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["forecasts"], 1)

        listing = self.client.get("/api/forecasts/")
        self.assertEqual(listing.status_code, 200)
        self.assertGreaterEqual(listing.data["count"], 1)

    def test_the_forecast_carries_its_explanation(self):
        start = dt.date(2026, 9, 1)
        for index in range(8 * 7):
            current = start + dt.timedelta(days=index)
            make_service(self.hall, current, attendance=500)
        service = make_service(self.hall, dt.date(2026, 10, 27), attendance=540)

        from apps.forecasting.services import forecast_service

        forecast_service(service)
        forecast = Forecast.objects.get(service=service)
        self.assertTrue(forecast.explanation)
        self.assertIn("expect about", forecast.explanation)
        self.assertEqual(len(forecast.input_signature), 64)


class AnalyticsEndpointTests(APITestCase):
    def test_demand_analytics_report_the_weekday_pattern(self):
        self.client.force_authenticate(self.manager)
        response = self.client.get(
            "/api/analytics/demand",
            {"start": self.on_date.isoformat(), "end": self.on_date.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["by_weekday"]), 7)

    def test_accuracy_analytics_report_the_summary(self):
        self.client.force_authenticate(self.manager)
        response = self.client.get(
            "/api/analytics/accuracy",
            {"start": self.on_date.isoformat(), "end": self.on_date.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("summary", response.data)
        self.assertIn("exact_mape_pct", response.data)


class MasterDataTests(APITestCase):
    def test_the_menu_endpoint_returns_the_dishes_on_a_menu(self):
        menu = make_menu()
        dish = make_dish("RICE_DISH", "Steamed Rice")
        add_dish_to_menu(menu, dish, meal="LUNCH", share="1.00")
        schedule_menu(menu, self.hall, self.on_date, meal="LUNCH")

        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/menu-schedules/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["dishes"][0]["dish"], "Steamed Rice")

    def test_the_dish_endpoint_exposes_the_derived_cost(self):
        dish = make_dish("RICE_DISH", "Steamed Rice")
        rice = make_ingredient("RICE", "Rice", "kg", "45")
        make_recipe(dish, [(rice, "0.180", "0")])

        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/dishes/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data["results"][0]["cost_per_portion"]), Decimal("8.10000000"))

    def test_the_indent_export_is_a_csv(self):
        menu = make_menu()
        dish = make_dish("RICE_DISH", "Steamed Rice")
        rice = make_ingredient("RICE", "Rice", "kg", "45")
        make_recipe(dish, [(rice, "0.180", "0")])
        add_dish_to_menu(menu, dish, meal="LUNCH", share="1.00")
        schedule_menu(menu, self.hall, self.on_date, meal="LUNCH")

        forecast = Forecast.objects.create(
            service=self.service,
            method="m", model_version="v",
            predicted_attendance=Decimal("500"),
            lower_bound=Decimal("460"), upper_bound=Decimal("540"),
            confidence_level=Decimal("0.8"), input_signature="c" * 64,
        )

        from apps.planning.services import generate_preparation_plan

        plan = generate_preparation_plan(self.service, forecast=forecast)

        self.client.force_authenticate(self.manager)
        response = self.client.get(f"/api/preparation-plans/{plan.id}/indent/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("Ingredient", response.content.decode())
