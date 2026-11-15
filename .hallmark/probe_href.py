import os, re, sys
sys.path.insert(0, r"D:\Haswanth\college\assignments\MessForecast")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django; django.setup()
from django.test import Client
from apps.accounts.models import User
HREF = re.compile(r'href="([^"#]+)"')
u = User.objects.get(username="crawl_admin")
c = Client(); c.force_login(u)
r = c.get("/dashboard/")
bad = []
for href in HREF.findall(r.content.decode()):
    if not href.startswith("/"):
        bad.append(href)
print("non-slash hrefs on /dashboard/:", bad[:20])
for href in HREF.findall(r.content.decode()):
    if href.startswith("/") and "/" not in href[1:]:
        print("single-segment:", href)
