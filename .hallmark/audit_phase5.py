"""Audit every requirement in the Phase 5 task against the running code.

Each line prints PASS or FAIL with what actually happened, so the gaps are
evidence rather than opinion.
"""

import os
import sys

sys.path.insert(0, r"D:\Haswanth\college\assignments\MessForecast")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import datetime as dt
from decimal import Decimal

from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.models import DiningHall
from apps.menu.models import Menu, MenuSchedule

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


def user(role, name, hall=None):
    u, _ = User.objects.get_or_create(
        username=name,
        defaults={"role": role, "email": f"{name}@mess.example"},
    )
    u.role = role
    u.email = f"{name}@mess.example"
    u.hall = hall
    u.set_password("pass12345")
    u.save()
    return u


print("=== 2. JWT authentication ===")
manager = user(User.Role.MESS_MANAGER, "audit_manager")
api = APIClient()

r = api.post("/api/auth/token/", {"username": "audit_manager", "password": "pass12345"}, format="json")
check("token obtain returns access + refresh", r.status_code == 200 and "access" in r.data and "refresh" in r.data, f"status {r.status_code}")
access, refresh = r.data.get("access", ""), r.data.get("refresh", "")

r = api.post("/api/auth/token/refresh/", {"refresh": refresh}, format="json")
check("refresh returns a new access token", r.status_code == 200 and "access" in r.data, f"status {r.status_code}")
rotated = r.data.get("refresh")
check("refresh ROTATES the refresh token", bool(rotated) and rotated != refresh, f"rotated={bool(rotated)}")

if rotated:
    r = api.post("/api/auth/token/refresh/", {"refresh": refresh}, format="json")
    check("the old refresh token is blacklisted after rotation", r.status_code != 200, f"status {r.status_code}")

r = api.post("/api/auth/logout/", {"refresh": refresh}, format="json")
check("logout blacklists the refresh token", r.status_code in (200, 204), f"status {r.status_code}")
r = api.post("/api/auth/token/refresh/", {"refresh": refresh}, format="json")
check("a blacklisted refresh token no longer works", r.status_code != 200, f"status {r.status_code}")

bearer = APIClient()
bearer.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
r = bearer.get("/api/auth/me/")
check("a bearer token reaches a protected endpoint", r.status_code == 200, f"status {r.status_code}")

r = APIClient().get("/api/auth/me/")
check("no token is refused", r.status_code in (401, 403), f"status {r.status_code}")

r = APIClient(headers={"HTTP_AUTHORIZATION": "Bearer not-a-real-token"}).get("/api/auth/me/")
check("a malformed token is refused", r.status_code in (401, 403), f"status {r.status_code}")

student = user(User.Role.STUDENT, "audit_student")
r = api.post("/api/auth/token/", {"username": "audit_student", "password": "pass12345"}, format="json")
student_access = r.data.get("access", "")
sb = APIClient()
sb.credentials(HTTP_AUTHORIZATION=f"Bearer {student_access}")
r = sb.post("/api/menus/", {"name": "Hacked", "code": "HACK"}, format="json")
check("a JWT does not bypass the role permissions", r.status_code in (401, 403), f"status {r.status_code}")

print("\n=== 3. Profile management ===")
r = api.post("/api/auth/token/", {"username": "audit_manager", "password": "pass12345"}, format="json")
mtok = r.data["access"]
ma = APIClient()
ma.credentials(HTTP_AUTHORIZATION=f"Bearer {mtok}")
r = ma.get("/api/accounts/profile/")
check("view own profile", r.status_code == 200 and r.data.get("username") == "audit_manager", f"status {r.status_code}")
check("profile shows role and student identifier", "role" in r.data and "student_identifier" in r.data)

r = ma.patch("/api/accounts/profile/", {"role": "ADMINISTRATOR"}, format="json")
check("cannot change own role", r.status_code in (400, 403), f"status {r.status_code}")
manager.refresh_from_db()
check("the role is unchanged after the attempt", manager.role == User.Role.MESS_MANAGER, f"role={manager.role}")

r = ma.patch("/api/accounts/profile/", {"email": "not-an-email"}, format="json")
check("the backend validates the email", r.status_code == 400, f"status {r.status_code}")

r = ma.post("/api/accounts/change-password/", {"old_password": "pass12345", "new_password": "newpass12345"}, format="json")
check("password change works", r.status_code in (200, 204), f"status {r.status_code}")

print("\n=== 4. Password reset ===")
c = Client()
r = c.post("/accounts/password-reset/request/", {"email": "nobody@example.com"})
r2 = c.post("/accounts/password-reset/request/", {"email": "audit_manager@mess.example"})
check("an unknown email is not revealed", r.status_code == r2.status_code, f"{r.status_code} vs {r2.status_code}")

print("\n=== 5/6/7. Dashboards, navigation, controls ===")
hall = DiningHall.objects.first()
for role, name in [
    (User.Role.STUDENT, "audit_s"),
    (User.Role.KITCHEN_STAFF, "audit_k"),
    (User.Role.FINANCE_OFFICER, "audit_f"),
    (User.Role.MESS_MANAGER, "audit_m"),
    (User.Role.MESS_ADMIN, "audit_ma"),
    (User.Role.ADMINISTRATOR, "audit_a"),
]:
    u = user(role, name)
    c = Client()
    c.force_login(u)
    r = c.get("/dashboard/")
    landed = r.get("Location", "") if r.status_code == 302 else r.request.get("PATH_INFO", "")
    expected = {
        User.Role.STUDENT: "/dashboard/student/",
        User.Role.KITCHEN_STAFF: "/kitchen/",
        User.Role.FINANCE_OFFICER: "/dashboard/finance/",
    }.get(role, "/dashboard/")
    check(f"{role} lands on {expected}", landed == expected, f"landed on {landed}")

print("\n=== 8. Student surface ===")
c = Client()
c.force_login(student)
r = c.get("/dashboard/student/")
body = r.content.decode()
check("the student dashboard renders", r.status_code == 200, f"status {r.status_code}")
for needle, label in [
    ("Today", "today's menu"),
    ("attendance", "attendance"),
    ("nouncement", "announcements"),
    ("Attendance history", "attendance history"),
]:
    check(f"the student dashboard shows {label}", needle.lower() in body.lower())

print("\n=== 9. Direct URL access ===")
PROTECTED = [
    ("dashboard-home", "/dashboard/"),
    ("dashboard-student", "/dashboard/student/"),
    ("dashboard-finance", "/dashboard/finance/"),
    ("console-forecast", "/console/forecast/"),
    ("console-attendance", "/console/attendance/"),
    ("console-menus", "/console/menus/"),
    ("console-recipes", "/console/recipes/"),
    ("console-dishes", "/console/dishes/"),
    ("console-reports", "/console/reports/"),
    ("console-settings", "/console/settings/"),
    ("dashboard-waste", "/dashboard/waste/"),
    ("dashboard-planning", "/dashboard/planning/"),
    ("kitchen-dashboard", "/kitchen/"),
]
for role, name in [(User.Role.STUDENT, "audit_s"), (User.Role.FINANCE_OFFICER, "audit_f")]:
    u = User.objects.get(username=name)
    c = Client()
    c.force_login(u)
    for label, path in PROTECTED:
        r = c.get(path)
        if label == "dashboard-home":
            continue  # routed by role, checked above
        if role == User.Role.STUDENT and label in ("dashboard-student",):
            continue
        if role == User.Role.FINANCE_OFFICER and label in ("dashboard-finance",):
            continue
        ok = r.status_code in (301, 302, 403)
        check(f"{role} is refused {path}", ok, f"status {r.status_code}")

print("\n=== Summary ===")
failed = [n for n, ok, _ in results if not ok]
print(f"  {len(results) - len(failed)} passed, {len(failed)} failed")
for n in failed:
    print(f"    FAILED: {n}")
