"""Celery tasks for forecasting and planning (Track P).

These are the scheduled jobs the specification calls for. With no broker
configured they run eagerly, so ``manage.py run_forecasts`` and the beat
schedule produce identical behaviour on a laptop and on a server.
"""

from __future__ import annotations

import datetime as dt

from celery import shared_task
from django.utils import timezone


@shared_task(name="forecasting.tasks.generate_daily_forecasts")
def generate_daily_forecasts(horizon_days: int = 7, today: str | None = None) -> dict:
    """Produce a rolling forecast for the next ``horizon_days`` days."""
    from apps.forecasting.services import generate_forecasts_for_range

    start = dt.date.fromisoformat(today) if today else timezone.localdate()
    end = start + dt.timedelta(days=horizon_days)
    results = generate_forecasts_for_range(start, end)
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "forecasts": len(results),
    }


@shared_task(name="forecasting.tasks.build_preparation_plans")
def build_preparation_plans(days: int = 2, today: str | None = None) -> dict:
    """Turn the latest forecasts into preparation plans and ingredient indents."""
    from apps.attendance.models import MealService
    from apps.planning.services import PlanningError, generate_preparation_plan

    start = dt.date.fromisoformat(today) if today else timezone.localdate()
    end = start + dt.timedelta(days=days)
    built = 0
    skipped = 0
    for service in MealService.objects.filter(date__gte=start, date__lte=end).select_related("hall"):
        try:
            generate_preparation_plan(service)
            built += 1
        except PlanningError:
            skipped += 1
    return {"built": built, "skipped": skipped}
