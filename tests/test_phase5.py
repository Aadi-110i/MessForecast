"""Phase 5 — authentication, profiles, password reset, role-based dashboards.

These tests exercise the end-to-end behaviour of the new authentication layer
and confirm the pre-existing Phase 4 behaviour is unaffected.
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import User, PasswordResetToken
from .factories import (
    add_dish_to_menu,
    make_dish,
    make_hall,
    make_menu,
    make_service,
    make_user,
    schedule_menu,
)


class JWTAuthBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.hall = make_hall()
        self.manager = make_user("manager", User.Role.MESS_MANAGER)
        self.student = make_user("student", User.Role.STUDENT, identifier="S001")
        self.student.set_password("studentpass1234")
        self.student.save()
        self.manager.set_password("managerpass1234")
        self.manager.save()


class JWTAuthenticationTests(JWTAuthBase):
    def _tokens(self, user, password):
        return self.client.post(
            reverse("auth-token-obtain"),
            {"username": user.username, "password": password},
            format="json",
        )

    def test_successful_login_returns_access_and_refresh(self):
        response = self._tokens(self.manager, "managerpass1234")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIn("user", response.data)
        self.assertEqual(response.data["user"]["role"], "MESS_MANAGER")

    def test_login_with_email_instead_of_username(self):
        self.manager.email = "manager@mess.example"
        self.manager.save()
        response = self.client.post(
            reverse("auth-token-obtain"),
            {"username": "manager@mess.example", "password": "managerpass1234"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_invalid_login_is_refused(self):
        response = self._tokens(self.manager, "wrong-password")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_credentials_is_refused(self):
        response = self.client.post(reverse("auth-token-obtain"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_expired_access_token_is_rejected(self):
        # Craft a token whose expiry is in the past.
        token = AccessToken()
        token["user_id"] = self.manager.id
        token.set_exp(from_time=dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc))
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + str(token))
        response = self.client.get(reverse("auth-me"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_token_issues_new_access(self):
        response = self._tokens(self.manager, "managerpass1234")
        refresh = response.data["refresh"]
        response = self.client.post(
            reverse("auth-token-refresh"), {"refresh": refresh}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_invalid_refresh_token_is_rejected(self):
        response = self.client.post(
            reverse("auth-token-refresh"), {"refresh": "not-a-token"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_blacklists_refresh_token(self):
        response = self._tokens(self.manager, "managerpass1234")
        refresh = response.data["refresh"]
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + response.data["access"])
        response = self.client.post(
            reverse("auth-logout"), {"refresh": refresh}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # The blacklisted refresh token can no longer be used.
        response = self.client.post(
            reverse("auth-token-refresh"), {"refresh": refresh}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthorized_api_request_is_refused(self):
        response = self.client.get(reverse("auth-me"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_authenticated_user(self):
        self.client.force_authenticate(self.manager)
        response = self.client.get(reverse("auth-me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "manager")
        self.assertEqual(response.data["role"], "MESS_MANAGER")

    def test_jwt_does_not_bypass_role_permissions(self):
        response = self._tokens(self.student, "studentpass1234")
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + response.data["access"])
        # A student holds no write capability for dishes.
        response = self.client.post(
            "/api/dishes/", {"name": "X", "code": "DISHX"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ProfileTests(JWTAuthBase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.manager)

    def test_view_own_profile(self):
        response = self.client.get(reverse("accounts-profile"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "manager")
        self.assertEqual(response.data["role"], "MESS_MANAGER")

    def test_update_own_profile(self):
        response = self.client.patch(
            reverse("accounts-profile"),
            {"first_name": "Mira", "email": "mira@mess.example"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.first_name, "Mira")
        self.assertEqual(self.manager.email, "mira@mess.example")

    def test_cannot_change_own_role(self):
        response = self.client.patch(
            reverse("accounts-profile"),
            {"role": User.Role.ADMINISTRATOR},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.role, User.Role.MESS_MANAGER)

    def test_update_own_profile_api_me(self):
        response = self.client.get(reverse("auth-me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "manager")

    def test_change_password(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(
            reverse("accounts-change-password"),
            {
                "old_password": "managerpass1234",
                "new_password": "newmanagerpass1234",
                "new_password_confirm": "newmanagerpass1234",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.check_password("newmanagerpass1234"))

    def test_change_password_wrong_old_password(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(
            reverse("accounts-change-password"),
            {
                "old_password": "nope",
                "new_password": "newmanagerpass1234",
                "new_password_confirm": "newmanagerpass1234",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_cannot_access_profile(self):
        self.client = APIClient()
        response = self.client.get(reverse("accounts-profile"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PasswordResetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user("resetuser", User.Role.STUDENT, identifier="S002")
        self.user.set_password("oldpass1234")
        self.user.email = "resetuser@mess.example"
        self.user.save()

    def test_forgot_password_unknown_email_does_not_reveal(self):
        response = self.client.post(
            reverse("password-reset-request"),
            {"email": "nobody@mess.example"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "If an account matches")

    def test_forgot_password_registered_email_sends_link(self):
        with patch(
            "apps.accounts.views.send_mail"
        ) as send_mail_mock:
            response = self.client.post(
                reverse("password-reset-request"),
                {"email": "ResetUser@Mess.Example"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(send_mail_mock.called)
        # Only one token should exist for the user.
        self.assertEqual(
            PasswordResetToken.objects.filter(user=self.user, used_at__isnull=True).count(),
            1,
        )

    def test_reset_with_valid_token(self):
        token = PasswordResetToken.create_for_user(self.user)
        response = self.client.get(
            reverse("password-reset-confirm", args=[token.token])
        )
        self.assertEqual(response.status_code, 200)

    def test_reset_with_invalid_token(self):
        response = self.client.get(reverse("password-reset-confirm", args=["nope"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid or has expired")

    def test_reset_with_expired_token(self):
        token = PasswordResetToken.create_for_user(self.user)
        token.created_at = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
        token.save()
        response = self.client.post(
            reverse("password-reset-complete", args=[token.token]),
            {
                "new_password": "brandnewpass1234",
                "new_password_confirm": "brandnewpass1234",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid or has expired")
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password("brandnewpass1234"))

    def test_reset_token_is_single_use(self):
        token = PasswordResetToken.create_for_user(self.user)
        self.client.post(
            reverse("password-reset-complete", args=[token.token]),
            {
                "new_password": "brandnewpass1234",
                "new_password_confirm": "brandnewpass1234",
            },
        )
        # The same token must not work again.
        response = self.client.post(
            reverse("password-reset-complete", args=[token.token]),
            {
                "new_password": "brandnewpass1234",
                "new_password_confirm": "brandnewpass1234",
            },
        )
        self.assertContains(response, "invalid or has expired")

    def test_password_must_meet_validators(self):
        token = PasswordResetToken.create_for_user(self.user)
        response = self.client.post(
            reverse("password-reset-complete", args=[token.token]),
            {"new_password": "weak", "new_password_confirm": "weak"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "characters")

    def test_passwords_must_match(self):
        token = PasswordResetToken.create_for_user(self.user)
        response = self.client.post(
            reverse("password-reset-complete", args=[token.token]),
            {"new_password": "brandnewpass1234", "new_password_confirm": "different"},
        )
        self.assertContains(response, "do not match")


class RoleDashboardTests(TestCase):
    """Every role reaches the dashboard it is permitted to use."""

    def setUp(self):
        self.client = APIClient()
        self.hall = make_hall()

    def _login(self, user):
        self.client.force_login(user)

    def test_student_lands_on_student_dashboard(self):
        user = make_user("s", User.Role.STUDENT)
        self._login(user)
        response = self.client.get(reverse("dashboard-home"))
        self.assertRedirects(response, reverse("dashboard-student"))

    def test_student_dashboard_renders(self):
        user = make_user("s", User.Role.STUDENT)
        self._login(user)
        dish = make_dish()
        menu = make_menu()
        add_dish_to_menu(menu, dish, meal="LUNCH")
        schedule_menu(menu, self.hall, dt.date.today(), meal="LUNCH")
        response = self.client.get(reverse("dashboard-student"))
        self.assertEqual(response.status_code, 200)
        # The student surface is a menu: the day's dishes are drawn, and the
        # dish that is on today is named on the page.
        self.assertContains(response, "On the menu today")
        self.assertContains(response, dish.name)
        self.assertContains(response, reverse("dashboard-student-menu"))

    def test_kitchen_staff_lands_on_kitchen(self):
        user = make_user("k", User.Role.KITCHEN_STAFF)
        user.hall = self.hall
        user.save()
        self._login(user)
        response = self.client.get(reverse("dashboard-home"))
        self.assertRedirects(response, reverse("kitchen-dashboard"))

    def test_finance_lands_on_finance_dashboard(self):
        user = make_user("f", User.Role.FINANCE_OFFICER)
        self._login(user)
        response = self.client.get(reverse("dashboard-home"))
        self.assertRedirects(response, reverse("dashboard-finance"))

    def test_finance_dashboard_is_read_only(self):
        user = make_user("f", User.Role.FINANCE_OFFICER)
        self._login(user)
        response = self.client.get(reverse("dashboard-finance"))
        self.assertEqual(response.status_code, 200)

    def test_manager_lands_on_overview(self):
        user = make_user("m", User.Role.MESS_MANAGER)
        self._login(user)
        response = self.client.get(reverse("dashboard-home"))
        self.assertEqual(response.status_code, 200)

    def test_administrator_lands_on_overview(self):
        user = make_user("a", User.Role.ADMINISTRATOR)
        self._login(user)
        response = self.client.get(reverse("dashboard-home"))
        self.assertEqual(response.status_code, 200)

    def test_mess_admin_lands_on_overview(self):
        user = make_user("ma", User.Role.MESS_ADMIN)
        self._login(user)
        response = self.client.get(reverse("dashboard-home"))
        self.assertEqual(response.status_code, 200)


class CapabilityNavigationTests(TestCase):
    """The rail hides destinations the role is not permitted to use."""

    def setUp(self):
        self.client = APIClient()

    def test_student_sees_only_permitted_destinations(self):
        user = make_user("s", User.Role.STUDENT)
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard-student"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        # A student gets the menu and nothing else: their own menu, the day
        # ahead and the notices. No console sections.
        self.assertIn(reverse("dashboard-student-menu"), html)
        self.assertNotIn(reverse("console-menus"), html)
        self.assertNotIn(reverse("console-recipes"), html)
        self.assertNotIn("Planning", html)
        self.assertNotIn("Settings", html)
        self.assertNotIn("Kitchen", html)

    def test_kitchen_staff_sees_no_financial_or_master_sections(self):
        user = make_user("k", User.Role.KITCHEN_STAFF)
        user.hall = make_hall()
        user.save()
        self.client.force_login(user)
        response = self.client.get(reverse("kitchen-dashboard"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn("Reports", html)
        self.assertNotIn("Settings", html)

    def test_finance_sees_only_permitted_sections(self):
        user = make_user("f", User.Role.FINANCE_OFFICER)
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard-finance"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Financial dashboard", html)
        self.assertIn("Menus", html)  # VIEW_MENU is held by finance
        # Finance holds no management or capture capability.
        self.assertNotIn("Settings", html)
        self.assertNotIn("Capture", html)

    def test_manager_sees_operational_sections(self):
        user = make_user("m", User.Role.MESS_MANAGER)
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard-home"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Forecast", html)
        self.assertIn("Waste", html)
        self.assertNotIn("Component library", html)


class RoleAccessTests(TestCase):
    """Roles cannot reach dashboards or APIs they are not permitted to use."""

    def setUp(self):
        self.client = APIClient()
        self.hall = make_hall()

    def test_student_cannot_reach_manager_dashboard(self):
        user = make_user("s", User.Role.STUDENT)
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard-home"))
        self.assertRedirects(response, reverse("dashboard-student"))

    def test_student_cannot_reach_finance_dashboard(self):
        user = make_user("s", User.Role.STUDENT)
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard-finance"))
        self.assertEqual(response.status_code, 403)

    def test_finance_cannot_reach_manager_overview(self):
        user = make_user("f", User.Role.FINANCE_OFFICER)
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard-home"))
        self.assertRedirects(response, reverse("dashboard-finance"))

    def test_cannot_access_another_users_profile_data(self):
        manager = make_user("mgr", User.Role.MESS_MANAGER)
        other = make_user("other", User.Role.STUDENT)
        self.client.force_authenticate(manager)
        # The profile endpoint always returns the requesting user's own data.
        response = self.client.get(reverse("accounts-profile"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "mgr")

    def test_student_api_cannot_write(self):
        user = make_user("s", User.Role.STUDENT)
        self.client.force_authenticate(user)
        response = self.client.post(
            "/api/dishes/", {"name": "X", "code": "DISHX"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_finance_api_is_read_only(self):
        user = make_user("f", User.Role.FINANCE_OFFICER)
        self.client.force_authenticate(user)
        response = self.client.get("/api/analytics/waste")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post("/api/dishes/", {"name": "X", "code": "DISHX"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class Phase5GapFixesTests(TestCase):
    """End-to-end verification of the Phase 5 security, UI and dashboard fixes."""

    def setUp(self):
        self.api = APIClient()
        self.hall = make_hall()

    def test_logout_with_invalid_refresh_token_returns_401(self):
        user = make_user("jwt_u", User.Role.STUDENT, identifier="S100")
        self.api.force_authenticate(user)
        response = self.api.post(
            reverse("auth-logout"), {"refresh": "not-a-valid-token"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_endpoint_exposes_capabilities(self):
        from apps.accounts.permissions import CAPABILITIES

        user = make_user("cap_u", User.Role.FINANCE_OFFICER)
        self.api.force_authenticate(user)
        response = self.api.get(reverse("auth-me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data["capabilities"]),
            CAPABILITIES[User.Role.FINANCE_OFFICER],
        )

    def test_profile_page_renders_edit_and_password_forms(self):
        user = make_user("prof_u", User.Role.STUDENT, identifier="S101")
        self.client.force_login(user)
        response = self.client.get(reverse("profile-page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="edit-profile-form"')
        self.assertContains(response, 'id="change-password-form"')

    def test_session_remains_valid_after_api_password_change(self):
        user = make_user("sess_u", User.Role.STUDENT, identifier="S102")
        user.set_password("InitialPass123!")
        user.save()
        self.client.force_login(user)
        response = self.client.post(
            reverse("accounts-change-password"),
            {
                "old_password": "InitialPass123!",
                "new_password": "UpdatedPass456!",
                "new_password_confirm": "UpdatedPass456!",
            },
        )
        self.assertEqual(response.status_code, 200)
        # Session must still be authenticated on the next web request.
        dash = self.client.get(reverse("dashboard-student"))
        self.assertEqual(dash.status_code, 200)

    def test_password_reset_enforces_auth_password_validators(self):
        user = make_user("val_u", User.Role.STUDENT, identifier="S103")
        user.set_password("ValidInitial123!")
        user.save()
        token = PasswordResetToken.create_for_user(user)
        # Numeric-only password should be rejected by NumericPasswordValidator.
        response = self.client.post(
            reverse("password-reset-complete", args=[token.token]),
            {
                "new_password": "1234567890",
                "new_password_confirm": "1234567890",
            },
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("ValidInitial123!"))

    def test_student_dashboard_stats_privacy_and_navigation(self):
        from apps.attendance.models import AttendanceRecord

        s1 = make_user("stu1", User.Role.STUDENT, identifier="S201")
        s2 = make_user("stu2", User.Role.STUDENT, identifier="S202")
        svc = make_service(self.hall, dt.date.today(), attendance=2)
        AttendanceRecord.objects.create(
            service=svc, student_identifier="S201", method="QR"
        )
        AttendanceRecord.objects.create(
            service=svc, student_identifier="S202", method="QR"
        )
        self.client.force_login(s1)
        response = self.client.get(reverse("dashboard-student"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Your meals", html)
        self.assertIn(reverse("profile-page"), html)
        self.assertNotIn(reverse("accounts-profile"), html)
        self.assertNotIn('<p class="rail-heading">Administration</p>', html)
        self.assertNotIn('<p class="rail-heading">Operations</p>', html)
        # Never show another student's attendance identifier or count.
        self.assertIn("1 record", html)
        self.assertNotIn("2 records", html)
        self.assertNotIn("S202", html)

    def test_finance_dashboard_shows_cost_rates_and_profile_link(self):
        from decimal import Decimal
        from apps.catalog.models import CostRate, Ingredient

        ing = Ingredient.objects.create(name="Basmati Rice", code="RICE_BAS", base_unit="KG")
        CostRate.objects.create(
            ingredient=ing,
            hall=self.hall,
            unit_cost=Decimal("82.50"),
            effective_from=dt.date.today() - dt.timedelta(days=5),
        )
        fin = make_user("fin_u", User.Role.FINANCE_OFFICER)
        self.client.force_login(fin)
        response = self.client.get(reverse("dashboard-finance"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Basmati Rice", html)
        self.assertIn("82.50", html)
        self.assertIn(reverse("profile-page"), html)
        self.assertNotIn(reverse("accounts-profile"), html)

    def test_menu_detail_hides_replace_form_without_plan_menu(self):
        menu = make_menu("Cycle X", "CYC_X")
        student = make_user("stu_m", User.Role.STUDENT, identifier="S301")
        self.client.force_login(student)
        response = self.client.get(reverse("console-menu-detail", args=[menu.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Replace dishes")

    def test_settings_refuses_finance_officer_and_allows_manager_event_form(self):
        fin = make_user("fin_s", User.Role.FINANCE_OFFICER)
        self.client.force_login(fin)
        self.assertEqual(self.client.get(reverse("console-settings")).status_code, 403)

        mgr = make_user("mgr_s", User.Role.MESS_MANAGER)
        self.client.force_login(mgr)
        response = self.client.get(reverse("console-settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("console-event-create"))

    def test_registration_code_issue_and_redeem_creates_user(self):
        from apps.accounts.registration import RegistrationCode

        admin = make_user("reg_admin", User.Role.MESS_ADMIN)
        self.client.force_login(admin)
        issue_res = self.client.post(
            reverse("registration-code-issue"),
            {
                "role": User.Role.STUDENT,
                "hall": self.hall.pk,
                "full_name": "Haswanth Kumar",
                "student_identifier": "S999",
            },
        )
        self.assertRedirects(issue_res, reverse("registration-console"))
        code = RegistrationCode.objects.get(student_identifier="S999")

        self.client.logout()
        reg_res = self.client.post(
            reverse("register-submit"),
            {
                "code": code.code,
                "username": "haswanth",
                "password": "StrongPassword123!",
                "password_confirm": "StrongPassword123!",
            },
        )
        self.assertEqual(reg_res.status_code, 200)
        created = User.objects.get(username="haswanth")
        self.assertEqual(created.role, User.Role.STUDENT)
        self.assertEqual(created.first_name, "Haswanth")
        self.assertEqual(created.last_name, "Kumar")
        self.assertEqual(created.student_identifier, "S999")

    def test_student_qr_checkin_marks_attendance_and_prevents_duplicates(self):
        from apps.attendance.models import AttendanceRecord

        svc = make_service(self.hall, dt.date.today(), attendance=0)
        student = make_user("qr_stu", User.Role.STUDENT, identifier="S500")
        self.client.force_login(student)

        dash = self.client.get(reverse("dashboard-student"))
        self.assertContains(dash, 'id="student-qr-reader"')
        self.assertContains(dash, "html5-qrcode.min.js")

        res1 = self.client.post(
            reverse("student-qr-checkin"),
            data=f'{{"qr_text": "MESSFORECAST:SERVICE:{svc.pk}"}}',
            content_type="application/json",
        )
        self.assertEqual(res1.status_code, 200)
        self.assertFalse(res1.json()["already_marked"])
        self.assertEqual(
            AttendanceRecord.objects.filter(service=svc, student_identifier="S500", method="QR").count(),
            1,
        )
        svc.refresh_from_db()
        self.assertEqual(svc.attendance_count, 1)

        # Second scan of the same service is idempotent (no double-count).
        res2 = self.client.post(
            reverse("student-qr-checkin"),
            data=f'{{"qr_text": "{{\\"service_id\\": {svc.pk}}}"}}',
            content_type="application/json",
        )
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.json()["already_marked"])
        svc.refresh_from_db()
        self.assertEqual(svc.attendance_count, 1)

    def test_student_qr_checkin_rejects_invalid_qr_and_non_students(self):
        student = make_user("qr_stu2", User.Role.STUDENT, identifier="S501")
        self.client.force_login(student)
        bad = self.client.post(
            reverse("student-qr-checkin"),
            data='{"qr_text": "INVALID-QR"}',
            content_type="application/json",
        )
        self.assertEqual(bad.status_code, 400)

        fin = make_user("qr_fin", User.Role.FINANCE_OFFICER)
        self.client.force_login(fin)
        denied = self.client.post(
            reverse("student-qr-checkin"),
            data='{"qr_text": "1"}',
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403)

    def test_scan_screen_renders_service_qr_generator_for_staff(self):
        make_service(self.hall, dt.date.today(), attendance=0)
        chef = make_user("qr_chef", User.Role.KITCHEN_STAFF)
        self.client.force_login(chef)
        res = self.client.get(reverse("scan-screen"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'id="service-qr-box"')
        self.assertContains(res, "qrcode.min.js")

