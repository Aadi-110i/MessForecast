import os
import sys

sys.path.insert(0, r"D:\Haswanth\college\assignments\MessForecast")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from django.test import Client
from django.urls import reverse

from apps.accounts.models import User

ROLES = [
    (User.Role.STUDENT, "student"),
    (User.Role.KITCHEN_STAFF, "chef"),
    (User.Role.FINANCE_OFFICER, "finance"),
    (User.Role.MESS_MANAGER, "manager"),
]

PROBES = [
    ("dashboard-home", "/dashboard/"),
    ("console-forecast", "/console/forecast/"),
    ("console-attendance", "/console/attendance/"),
    ("console-menus", "/console/menus/"),
    ("console-recipes", "/console/recipes/"),
    ("console-reports", "/console/reports/"),
    ("console-settings", "/console/settings/"),
    ("design-system", "/console/design-system/"),
    ("dashboard-waste", "/dashboard/waste/"),
    ("dashboard-planning", "/dashboard/planning/"),
    ("kitchen-dashboard", "/kitchen/"),
]

for role, username in ROLES:
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={"role": role, "email": f"{username}@mess.test"},
    )
    user.set_password("pass12345")
    user.role = role
    user.save()

    c = Client()
    c.force_login(user)
    print(f"\n=== {role} ({username}) ===")
    for name, path in PROBES:
        r = c.get(path)
        flag = "" if r.status_code in (200, 302) else "   <-- denied"
        print(f"  {r.status_code}  {path}{flag}")
