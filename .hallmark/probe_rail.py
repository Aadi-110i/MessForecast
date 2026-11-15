import os
import sys

sys.path.insert(0, r"D:\Haswanth\college\assignments\MessForecast")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from django.test import Client

from apps.accounts.models import User

DESTINATIONS = [
    ("Overview", "/dashboard/"),
    ("Forecast", "/console/forecast/"),
    ("Attendance", "/console/attendance/"),
    ("Menus", "/console/menus/"),
    ("Recipes", "/console/recipes/"),
    ("Dishes", "/console/dishes/"),
    ("Planning", "/dashboard/planning/"),
    ("Waste", "/dashboard/waste/"),
    ("Reports", "/console/reports/"),
    ("Settings", "/console/settings/"),
    ("Data quality", "/dashboard/data-quality/"),
    ("Component library", "/console/design-system/"),
    ("Kitchen", "/kitchen/"),
    ("Capture", "/scan/"),
]

for role in (User.Role.STUDENT, User.Role.KITCHEN_STAFF, User.Role.FINANCE_OFFICER, User.Role.MESS_MANAGER, User.Role.ADMINISTRATOR):
    user = User.objects.filter(role=role).first()
    if user is None:
        continue
    c = Client()
    c.force_login(user)
    html = c.get("/dashboard/").content.decode()
    offered = [name for name, href in DESTINATIONS if f'href="{href}"' in html]
    print(f"  {role:18} rail offers {len(offered):2}/{len(DESTINATIONS)}: {', '.join(offered)}")
