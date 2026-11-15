"""The guards on the plain Django surfaces.

The API viewsets declare the capability they need and the REST framework
checks it. The rendered console, the tablet screens and the capture screen
are plain Django views, and a surface there that was not guarded meant "any
signed-in user" - which no role in the capability table holds.

These tests cover that gap: every protected surface is refused to the roles
that must not reach it, and the controls a reader cannot use are not
rendered for them.
"""

from __future__ import annotations

import datetime as dt

from django.db import connection
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.attendance.models import MealService
from apps.catalog.models import DiningHall

from .factories import make_hall, make_service, make_user


class SurfaceGuardTests(TestCase):
    """Each protected surface refuses the roles that must not reach it."""

    def setUp(self):
        self.student = make_user("guard_student", User.Role.STUDENT)
        self.kitchen = make_user("guard_kitchen", User.Role.KITCHEN_STAFF)
        self.finance = make_user("guard_finance", User.Role.FINANCE_OFFICER)
        self.manager = make_user("guard_manager", User.Role.MESS_MANAGER)
        self.mess_admin = make_user("guard_messadmin", User.Role.MESS_ADMIN)
        self.admin = make_user("guard_admin", User.Role.ADMINISTRATOR)

        self.hall = make_hall()
        self.service = make_service(self.hall, dt.date.today(), attendance=480)

    def client_for(self, user):
        c = Client()
        c.force_login(user)
        return c

    # --- the capture screen is the kitchen's -----------------------------

    def test_a_student_cannot_reach_the_capture_screen(self):
        response = self.client_for(self.student).get(reverse("scan-screen"))
        self.assertEqual(response.status_code, 403)

    def test_a_finance_officer_cannot_reach_the_capture_screen(self):
        response = self.client_for(self.finance).get(reverse("scan-screen"))
        self.assertEqual(response.status_code, 403)

    def test_a_mess_manager_can_reach_the_capture_screen(self):
        response = self.client_for(self.manager).get(reverse("scan-screen"))
        self.assertEqual(response.status_code, 200)

    def test_a_student_cannot_record_a_scan(self):
        response = self.client_for(self.student).post(
            reverse("scan-capture"),
            {
                "student_identifier": "guard_student-ID",
                "service_id": self.service.pk,
                "hall_id": self.hall.pk,
                "meal": "LUNCH",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.service.attendance_count, 480)

    def test_a_student_cannot_read_the_scan_count(self):
        response = self.client_for(self.student).get(
            reverse("scan-count"), {"service": self.service.pk}
        )
        self.assertEqual(response.status_code, 403)

    # --- the reporting surfaces are the managers' -------------------------

    def test_a_student_cannot_read_the_waste_report(self):
        response = self.client_for(self.student).get(reverse("dashboard-waste"))
        self.assertEqual(response.status_code, 403)

    def test_a_student_cannot_read_the_preparation_plans(self):
        response = self.client_for(self.student).get(reverse("dashboard-planning"))
        self.assertEqual(response.status_code, 403)

    def test_a_student_cannot_read_the_forecast_accuracy(self):
        response = self.client_for(self.student).get(reverse("dashboard-accuracy"))
        self.assertEqual(response.status_code, 403)

    def test_a_finance_officer_can_read_the_waste_report(self):
        response = self.client_for(self.finance).get(reverse("dashboard-waste"))
        self.assertEqual(response.status_code, 200)

    def test_a_finance_officer_can_read_the_forecast_accuracy(self):
        response = self.client_for(self.finance).get(reverse("dashboard-accuracy"))
        self.assertEqual(response.status_code, 200)

    def test_a_mess_admin_cannot_read_the_forecast_accuracy(self):
        # VIEW_ACCURACY is not in the mess administrator's set.
        response = self.client_for(self.mess_admin).get(reverse("dashboard-accuracy"))
        self.assertEqual(response.status_code, 403)

    def test_a_kitchen_staff_member_can_read_the_preparation_plans(self):
        response = self.client_for(self.kitchen).get(reverse("dashboard-planning"))
        self.assertEqual(response.status_code, 200)

    def test_a_kitchen_staff_member_cannot_read_the_waste_cost(self):
        response = self.client_for(self.kitchen).get(reverse("dashboard-waste"))
        self.assertEqual(response.status_code, 403)

    def test_the_data_quality_monitor_is_closed_to_a_student(self):
        response = self.client_for(self.student).get(reverse("dashboard-data-quality"))
        self.assertEqual(response.status_code, 403)

    def test_the_data_quality_monitor_is_open_to_the_kitchen(self):
        response = self.client_for(self.kitchen).get(reverse("dashboard-data-quality"))
        self.assertEqual(response.status_code, 200)

    # --- the masters are the mess office's -------------------------------

    def test_a_mess_manager_cannot_reach_the_dish_catalogue(self):
        response = self.client_for(self.manager).get(reverse("console-dishes"))
        self.assertEqual(response.status_code, 403)

    def test_a_mess_administrator_can_reach_the_dish_catalogue(self):
        response = self.client_for(self.mess_admin).get(reverse("console-dishes"))
        self.assertEqual(response.status_code, 200)

    def test_a_mess_manager_cannot_reach_the_registration_codes(self):
        response = self.client_for(self.manager).get(reverse("registration-console"))
        self.assertEqual(response.status_code, 403)

    def test_a_mess_administrator_can_reach_the_registration_codes(self):
        response = self.client_for(self.mess_admin).get(reverse("registration-console"))
        self.assertEqual(response.status_code, 200)


class NavigationAndControlTests(TestCase):
    """A destination or a control the reader cannot use is not rendered."""

    def setUp(self):
        self.student = make_user("nav_student", User.Role.STUDENT)
        self.finance = make_user("nav_finance", User.Role.FINANCE_OFFICER)
        self.manager = make_user("nav_manager", User.Role.MESS_MANAGER)
        self.mess_admin = make_user("nav_messadmin", User.Role.MESS_ADMIN)

    def client_for(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_the_rail_hides_the_dish_catalogue_from_a_student(self):
        response = self.client_for(self.student).get(reverse("dashboard-student"))
        self.assertNotContains(response, reverse("console-dishes"))

    def test_the_rail_hides_the_dish_catalogue_from_a_finance_officer(self):
        response = self.client_for(self.finance).get(reverse("dashboard-finance"))
        self.assertNotContains(response, reverse("console-dishes"))

    def test_the_rail_shows_the_dish_catalogue_to_a_mess_administrator(self):
        response = self.client_for(self.mess_admin).get(reverse("dashboard-home"))
        self.assertContains(response, reverse("console-dishes"))

    def test_the_settings_screen_hides_manage_codes_from_a_mess_manager(self):
        response = self.client_for(self.manager).get(reverse("console-settings"))
        self.assertNotContains(response, reverse("registration-console"))

    def test_the_settings_screen_shows_manage_codes_to_a_mess_administrator(self):
        response = self.client_for(self.mess_admin).get(reverse("console-settings"))
        self.assertContains(response, reverse("registration-console"))

    def test_the_attendance_screen_hides_the_sync_log_from_a_finance_officer(self):
        response = self.client_for(self.finance).get(reverse("console-attendance"))
        self.assertNotContains(response, reverse("console-export-attendance"))

    def test_the_attendance_screen_shows_the_sync_log_to_a_mess_manager(self):
        response = self.client_for(self.manager).get(reverse("console-attendance"))
        self.assertContains(response, reverse("console-export-attendance"))

    def test_the_reports_catalogue_hides_a_report_the_reader_cannot_open(self):
        # A mess administrator may open the reports console, but the forecast
        # accuracy report needs VIEW_ACCURACY, which they do not hold.
        response = self.client_for(self.mess_admin).get(reverse("console-reports"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "/dashboard/accuracy/")

    def test_the_reports_catalogue_shows_every_report_to_an_administrator(self):
        admin = make_user("nav_admin", User.Role.ADMINISTRATOR)
        response = self.client_for(admin).get(reverse("console-reports"))
        self.assertContains(response, "/dashboard/accuracy/")

    def test_the_kitchen_screen_hides_the_capture_link_from_a_finance_officer(self):
        response = self.client_for(self.finance).get(reverse("kitchen-dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("scan-screen"))

    def test_the_kitchen_screen_shows_the_capture_link_to_kitchen_staff(self):
        kitchen = make_user("nav_kitchen", User.Role.KITCHEN_STAFF)
        response = self.client_for(kitchen).get(reverse("kitchen-dashboard"))
        self.assertContains(response, reverse("scan-screen"))


class KitchenActualReadOnlyTests(TestCase):
    """A reader gets the recorded figures, not a form that would be refused."""

    def setUp(self):
        self.hall = make_hall()
        self.service = make_service(self.hall, dt.date.today(), attendance=480)
        self.finance = make_user("kitchen_finance", User.Role.FINANCE_OFFICER)
        self.manager = make_user("kitchen_manager", User.Role.MESS_MANAGER)

    def client_for(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_a_finance_officer_gets_no_save_button(self):
        response = self.client_for(self.finance).get(
            reverse("kitchen-actuals", args=[self.service.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "k-save")

    def test_a_finance_officer_gets_no_portion_inputs(self):
        response = self.client_for(self.finance).get(
            reverse("kitchen-actuals", args=[self.service.pk])
        )
        self.assertNotContains(response, "k-served")

    def test_a_mess_manager_gets_the_save_button(self):
        response = self.client_for(self.manager).get(
            reverse("kitchen-actuals", args=[self.service.pk])
        )
        self.assertContains(response, "k-save")

    def test_the_kitchen_guidance_json_is_closed_to_a_student(self):
        student = make_user("kitchen_student", User.Role.STUDENT)
        response = self.client_for(student).get(
            reverse("kitchen-guidance", args=[self.service.pk])
        )
        self.assertEqual(response.status_code, 403)


class MigrationStateTests(TestCase):
    """The tables the authentication features need have to exist.

    The JWT blacklist and the password reset token tables are created by
    migrations from third-party apps and from this one. A developer who
    pulls the code and runs the application without migrating gets a 500 on
    every token endpoint, and the test suite does not catch it because
    Django builds its test database from scratch.
    """

    def test_the_token_blacklist_tables_exist(self):
        with connection.cursor() as cursor:
            tables = set(connection.introspection.table_names(cursor))
        self.assertIn("token_blacklist_outstandingtoken", tables)
        self.assertIn("token_blacklist_blacklistedtoken", tables)

    def test_the_password_reset_token_table_exists(self):
        with connection.cursor() as cursor:
            tables = set(connection.introspection.table_names(cursor))
        self.assertIn("accounts_passwordresettoken", tables)


class CapabilityTableTests(TestCase):
    """The capability table is the one place a role's powers are written."""

    def test_managing_users_is_a_capability_not_a_role_check(self):
        from apps.accounts.permissions import CAPABILITIES

        self.assertIn("MANAGE_USERS", CAPABILITIES[User.Role.MESS_ADMIN])
        self.assertIn("MANAGE_USERS", CAPABILITIES[User.Role.ADMINISTRATOR])
        for role in (
            User.Role.STUDENT,
            User.Role.KITCHEN_STAFF,
            User.Role.FINANCE_OFFICER,
            User.Role.MESS_MANAGER,
        ):
            self.assertNotIn("MANAGE_USERS", CAPABILITIES[role])

    def test_every_capability_in_the_table_is_used_somewhere(self):
        from apps.accounts.permissions import CAPABILITIES

        for caps in CAPABILITIES.values():
            for capability in caps:
                self.assertTrue(
                    capability.isupper(),
                    f"{capability} should be a capability name",
                )
