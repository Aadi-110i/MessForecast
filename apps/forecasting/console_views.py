"""Forecast console.

The forward-looking screen: what the engine expects for the week ahead,
how confident it is, and why it says what it says. The forecast stores its
own workings — the base level, the weekday factor, the event factor and the
trend — so the number can be explained rather than trusted blindly. That
explanation is the point of this screen.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.accounts.permissions import has_capability
from apps.attendance.models import MealService
from apps.core.console import active_halls, selected_hall
from apps.forecasting.models import Forecast


@login_required
@require_GET
def forecast_console(request):
    """The forecast dashboard: the week ahead, band by band."""
    if not has_capability(request.user, "VIEW_FORECAST"):
        return JsonResponse({"detail": "Not permitted"}, status=403)

    today = dt.date.today()
    horizon = int(request.GET.get("days") or 7)
    horizon = max(1, min(horizon, 28))
    end = today + dt.timedelta(days=horizon)

    hall = selected_hall(request)

    services = (
        MealService.objects.filter(date__gte=today, date__lte=end)
        .select_related("hall", "forecast", "preparation_plan")
        .order_by("date", "meal")
    )
    if hall is not None:
        services = services.filter(hall=hall)

    rows = []
    band_low = None
    band_high = None
    for service in services:
        forecast = getattr(service, "forecast", None)
        if forecast is None:
            rows.append({"service": service, "forecast": None})
            continue
        rows.append({"service": service, "forecast": forecast})
        low = float(forecast.lower_bound)
        high = float(forecast.upper_bound)
        band_low = low if band_low is None else min(band_low, low)
        band_high = high if band_high is None else max(band_high, high)

    # The chart needs a plain series, so it is built here rather than in
    # the template: the viewBox arithmetic belongs to the data, not the view.
    band = [
        {
            "label": r["service"].date.isoformat(),
            "predicted": float(r["forecast"].predicted_attendance) if r["forecast"] else 0,
            "lower": float(r["forecast"].lower_bound) if r["forecast"] else 0,
            "upper": float(r["forecast"].upper_bound) if r["forecast"] else 0,
            "meal": r["service"].get_meal_display(),
            "hall": r["service"].hall.code,
        }
        for r in rows
    ]

    coverage = services.count()
    with_forecast = sum(1 for r in rows if r["forecast"])
    total_predicted = sum(
        (r["forecast"].predicted_attendance for r in rows if r["forecast"]), Decimal("0")
    )

    context = {
        "today": today,
        "end": end,
        "horizon": horizon,
        "hall": hall,
        "halls": active_halls(),
        "rows": rows,
        "band": band,
        "band_low": band_low,
        "band_high": band_high,
        "figures": [
            {
                "label": "Services ahead",
                "value": coverage,
                "note": f"{with_forecast} of them forecast",
            },
            {
                "label": "Expected turnout",
                "value": f"{float(total_predicted):,.0f}",
                "note": "Summed over every service in the window",
            },
            {
                "label": "Widest range",
                "value": f"{float(band_high - band_low):,.0f}" if band_low is not None else "—",
                "note": "How much room the kitchen has on the worst day",
            },
            {
                "label": "Forecast coverage",
                "value": f"{round(with_forecast / coverage * 100, 1) if coverage else 0.0}%",
                "note": f"{coverage - with_forecast} services still need one",
            },
        ],
        "coverage": {
            "services": coverage,
            "with_forecast": with_forecast,
            "missing": coverage - with_forecast,
            "pct": round(with_forecast / coverage * 100, 1) if coverage else 0.0,
        },
        "coverage_specs": [
            {"name": "Services", "value": coverage},
            {"name": "With a forecast", "value": with_forecast},
            {"name": "Still to forecast", "value": coverage - with_forecast},
            {"name": "Coverage", "value": f"{round(with_forecast / coverage * 100, 1) if coverage else 0.0}%"},
        ],
        "total_predicted": total_predicted,
        "events": _upcoming_events(today, end),
    }
    return render(request, "console/forecast.html", context)


def _upcoming_events(today: dt.date, end: dt.date) -> list[dict]:
    """Calendar events inside the horizon, because they move the number."""
    from apps.events.models import CalendarEvent

    events = (
        CalendarEvent.objects.filter(is_active=True, start_date__lte=end, end_date__gte=today)
        .order_by("start_date")
    )
    return [
        {
            "event": event,
            "name": event.name,
            "type": event.get_event_type_display(),
            "factor": event.impact_factor,
            "start": event.start_date,
            "end": event.end_date,
        }
        for event in events
    ]
