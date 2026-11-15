import os
import sys

sys.path.insert(0, r"D:\Haswanth\college\assignments\MessForecast")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from django.test import Client

from apps.accounts.models import User
from apps.catalog.models import DiningHall
from apps.menu.models import Menu, MenuSchedule

user = User.objects.get(username="manager")
client = Client()
client.force_login(user)

hall = DiningHall.objects.first()
menus = list(Menu.objects.order_by("code")[:2])
print(f"hall={hall.code} menus={[m.code for m in menus]}")

url = "/console/schedule/assign/"

# A slot that is already taken by the first cycle.
existing = MenuSchedule.objects.filter(hall=hall).first()
if existing is None:
    print("no schedule rows to test against")
    raise SystemExit

on_date = existing.date
meal = existing.meal
print(f"existing slot: {on_date} {meal} -> {existing.menu.code}")

# Assign the OTHER cycle to the same hall + date + meal.
other = menus[0] if existing.menu_id != menus[0].pk else menus[1]
r = client.post(url, {"menu": other.pk, "hall": hall.pk, "date": on_date.isoformat(), "meal": meal})
print(f"replace with another cycle -> {r.status_code}")
if r.status_code != 200:
    print("  body:", r.content[:300])

after = MenuSchedule.objects.filter(hall=hall, date=on_date, meal=meal).first()
print(f"after: {after.menu.code if after else 'none'} (expected {other.code})")
