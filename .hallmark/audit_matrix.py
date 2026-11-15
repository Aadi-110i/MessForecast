"""Every named URL, every role, every status.

A surface that answers 200 to a role is a surface the rail did not offer
that role. The rail is a convenience; the server is the boundary.
"""

import os
import sys

sys.path.insert(0, r"D:\Haswanth\college\assignments\MessForecast")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from django.test import Client
from django.urls import get_resolver

from apps.accounts.models import User

# Concrete paths for the named routes, so they can be requested.
PATHS = {
    "dashboard-home": "/dashboard/",
    "dashboard-student": "/dashboard/student/",
    "dashboard-finance": "/dashboard/finance/",
    "dashboard-waste": "/dashboard/waste/",
    "dashboard-accuracy": "/dashboard/accuracy/",
    "dashboard-planning": "/dashboard/planning/",
    "dashboard-data-quality": "/dashboard/data-quality/",
    "console-menus": "/console/menus/",
    "console-recipes": "/console/recipes/",
    "console-dishes": "/console/dishes/",
    "console-attendance": "/console/attendance/",
    "console-forecast": "/console/forecast/",
    "console-reports": "/console/reports/",
    "console-settings": "/console/settings/",
    "design-system": "/console/design-system/",
    "kitchen-dashboard": "/kitchen/",
    "registration-console": "/accounts/codes/",
    "accounts-profile": "/accounts/profile/",
    "password-reset": "/accounts/password-reset/",
    "scan": "/scan/",
}

ROLES = [
    (User.Role.STUDENT, "STUDENT"),
    (User.Role.KITCHEN_STAFF, "KITCHEN STAFF"),
    (User.Role.FINANCE_OFFICER, "FINANCE"),
    (User.Role.MESS_MANAGER, "MESS MANAGER"),
    (User.Role.MESS_ADMIN, "MESS ADMIN"),
    (User.Role.ADMINISTRATOR, "ADMIN"),
]

clients = {}
for role, label in ROLES:
    name = f"probe_{label.lower().replace(' ', '_')}"
    u, _ = User.objects.get_or_create(
        username=name, defaults={"role": role, "email": f"{name}@mess.example"}
    )
    u.role = role
    u.set_password("pass12345")
    u.save()
    c = Client()
    c.force_login(u)
    clients[label] = c

print(f"{'route':26} " + " ".join(f"{label[:11]:>12}" for _, label in ROLES))
print("-" * 106)
for name, path in PATHS.items():
    row = []
    for _, label in ROLES:
        try:
            r = clients[label].get(path)
            code = r.status_code
            if code == 302:
                code = f"302->{r.get('Location', '').replace('/dashboard/', '').replace('/console/', '')[:9]}"
        except Exception as exc:
            code = type(exc).__name__[:12]
        row.append(f"{str(code):>12}")
    print(f"{name:26} " + " ".join(row))
