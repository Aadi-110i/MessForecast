import os
import sys

sys.path.insert(0, r"D:\Haswanth\college\assignments\MessForecast")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from django.urls import reverse

for name in [
    "accounts-profile",
    "console-dishes",
    "console-schedule-day",
    "console-schedule-week",
    "console-event-create",
    "password-reset",
    "registration-console",
]:
    try:
        print(f"  reverse({name!r}) -> {reverse(name)}")
    except Exception as exc:
        print(f"  reverse({name!r}) -> ERROR {type(exc).__name__}: {exc}")

# What does the topbar Profile button actually point at?
from django.test import Client

from apps.accounts.models import User

user = User.objects.filter(is_superuser=False).first() or User.objects.first()
c = Client()
c.force_login(user)
html = c.get("/dashboard/").content.decode()
i = html.find("Profile")
print("\n--- topbar around Profile ---")
print(html[max(0, i - 300):i + 200])
