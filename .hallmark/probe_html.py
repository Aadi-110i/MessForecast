import os
import sys

sys.path.insert(0, r"D:\Haswanth\college\assignments\MessForecast")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from django.test import Client

from apps.accounts.models import User

user = User.objects.get(username="sysadmin")
c = Client()
c.force_login(user)
html = c.get("/console/settings/").content.decode()

i = html.find("North Block Mess")
print("--- html around the hall row ---")
print(html[i - 400:i + 500])
