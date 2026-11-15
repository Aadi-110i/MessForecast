import os
import sys

sys.path.insert(0, r"D:\Haswanth\college\assignments\MessForecast")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.test import Client

c = Client()
c.login(username="sysadmin", password="messdemo")
html = c.get("/console/settings/").content.decode()
i = html.find("The window")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
print(html[i - 200:i + 1000])
