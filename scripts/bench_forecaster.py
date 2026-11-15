"""Measure the forecaster's hot path against the seeded database.

Reports the real wall-clock cost of producing one forecast and of a full
batch, so the documentation quotes measured numbers rather than estimates.

    python scripts/bench_forecaster.py
"""

from __future__ import annotations

import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from apps.attendance.models import MealService  # noqa: E402
from apps.forecasting.services import forecast_service  # noqa: E402


def main() -> int:
    services = list(
        MealService.objects.select_related("hall").order_by("-date")[:60]
    )
    if not services:
        print("No meal services in the database. Run `manage.py seed_demo` first.")
        return 1

    # Warm the caches the engine reads.
    for service in services[:5]:
        forecast_service(service)

    samples = []
    for service in services:
        start = time.perf_counter()
        forecast_service(service)
        samples.append((time.perf_counter() - start) * 1000)

    samples.sort()
    count = len(samples)
    print(f"forecast_service() over {count} services")
    print(f"  mean   : {statistics.mean(samples):.3f} ms")
    print(f"  median : {statistics.median(samples):.3f} ms")
    print(f"  p95    : {samples[min(int(count * 0.95), count) - 1]:.3f} ms")
    print(f"  max    : {samples[-1]:.3f} ms")

    # A seven-day week across two halls is what the daily Celery job produces.
    week = services[:42]
    start = time.perf_counter()
    for service in week:
        forecast_service(service)
    elapsed = time.perf_counter() - start
    print()
    print(f"{len(week)} forecasts in {elapsed * 1000:.1f} ms "
          f"({elapsed / max(len(week), 1) * 1000:.3f} ms each)")
    print(f"a 7-day x 2-hall week (42 services) takes about {elapsed:.3f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
