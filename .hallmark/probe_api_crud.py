import os
import sys

sys.path.insert(0, r"D:\Haswanth\college\assignments\MessForecast")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.models import Dish

client = APIClient(raise_request_exception=False)

for role, username in [
    (User.Role.MESS_MANAGER, "manager"),
    (User.Role.MESS_ADMIN, "admin"),
    (User.Role.ADMINISTRATOR, "sysadmin"),
]:
    user = User.objects.get(username=username)
    client.force_authenticate(user)
    print(f"\n=== {role} ({username}) ===")

    used = Dish.objects.filter(menu_items__isnull=False).first()
    free = Dish.objects.filter(menu_items__isnull=True).first()

    r = client.post("/api/dishes/", {"name": "Probe Curry", "code": "PROBE1", "category": "VEG"}, format="json")
    print(f"  POST   /api/dishes/            -> {r.status_code}")
    new_id = r.data.get("id") if r.status_code < 300 else None

    if new_id:
        r = client.put(f"/api/dishes/{new_id}/", {"name": "Probe Curry v2", "code": "PROBE1", "category": "VEG"}, format="json")
        print(f"  PUT    /api/dishes/{{id}}/       -> {r.status_code}")
        r = client.delete(f"/api/dishes/{new_id}/")
        print(f"  DELETE /api/dishes/{{id}}/       -> {r.status_code}  (unused dish)")
    else:
        print(f"         -> {str(r.data)[:80]}")

    if used:
        r = client.delete(f"/api/dishes/{used.id}/")
        print(f"  DELETE /api/dishes/{{in use}}/   -> {r.status_code}  (dish on a menu)")
        r = client.delete(f"/api/dishes/{free.id}/") if free else None
        if r is not None:
            print(f"  DELETE /api/dishes/{{unused}}/   -> {r.status_code}  (on no menu)")
