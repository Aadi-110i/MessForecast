import os
import sys

sys.path.insert(0, r"D:\Haswanth\college\assignments\MessForecast")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from django.test import Client

from apps.accounts.models import User

WRITE_AFFORDANCES = [
    ("console-recipe-version-form", "/console/recipes/311/", "Create version"),
    ("console-menu-create-form", "/console/menus/create/", "Create"),
    ("console-registration-codes", "/accounts/codes/", "Issue code"),
    ("console-settings", "/console/settings/", "Service levels"),
    ("console-menus", "/console/menus/", "Assign"),
]

for role, username in [
    (User.Role.STUDENT, "student"),
    (User.Role.FINANCE_OFFICER, "finance"),
    (User.Role.MESS_MANAGER, "manager"),
]:
    user = User.objects.get(username=username)
    c = Client()
    c.force_login(user)
    print(f"\n=== {role} ===")
    for label, path, needle in WRITE_AFFORDANCES:
        r = c.get(path)
        if r.status_code != 200:
            print(f"  {r.status_code}  {label:32} (no page)")
            continue
        body = r.content.decode()
        has = needle.lower() in body.lower()
        print(f"  {r.status_code}  {label:32} shows {needle!r}: {'YES' if has else 'no'}")

    # What does the rail offer this role?
    r = c.get("/dashboard/")
    body = r.content.decode()
    links = [
        ("Overview", "/dashboard/"),
        ("Forecast", "/console/forecast/"),
        ("Attendance", "/console/attendance/"),
        ("Menus", "/console/menus/"),
        ("Recipes", "/console/recipes/"),
        ("Planning", "/dashboard/planning/"),
        ("Waste", "/dashboard/waste/"),
        ("Reports", "/console/reports/"),
        ("Settings", "/console/settings/"),
        ("Data quality", "/dashboard/data-quality/"),
        ("Component library", "/console/design-system/"),
        ("Kitchen", "/kitchen/"),
        ("Capture", "/scan/"),
    ]
    visible = [name for name, href in links if f'href="{href}"' in body]
    print(f"  rail offers {len(visible)}/13 destinations: {', '.join(visible)}")
