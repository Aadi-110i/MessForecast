import os
import sys

sys.path.insert(0, r"D:\Haswanth\college\assignments\MessForecast")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from apps.catalog.models import DiningHall
from apps.core import demo_data

for spec in demo_data.HALLS:
    hall = DiningHall.objects.filter(code=spec["code"]).first()
    if hall is None:
        print(f"  {spec['code']}: no hall, skipped")
        continue
    if hall.location != spec.get("location", ""):
        hall.location = spec.get("location", "")
        hall.save(update_fields=["location", "updated_at"])
        print(f"  {spec['code']}: location set")
    else:
        print(f"  {spec['code']}: already set")

for hall in DiningHall.objects.all().order_by("code"):
    print(f"  {hall.code}: {hall.name} — {hall.location or '(no location)'}")
