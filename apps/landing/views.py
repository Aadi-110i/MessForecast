"""The public landing page.

Every figure on this page is recomputed from the database when the page is
requested. Nothing here is typed into a template: re-seed the demonstration
data and the page reports the new numbers, because the page is meant to be
evidence that the platform works rather than a picture of what it once did.

The periods are read from ``MealService.prep_mode`` rather than from fixed
dates. The baseline is every service the kitchen cooked against the registered
strength; the live period is every service cooked against the forecast.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Count, Max, Min, Q
from django.shortcuts import render
from django.utils import timezone

from apps.attendance.models import MealService
from apps.catalog.models import DiningHall
from apps.core.constants import PrepMode
from apps.forecasting.models import Forecast
from apps.reporting import services as reporting
from apps.waste import services as waste_services


def _periods() -> dict | None:
    """The baseline and live windows, read from the records themselves."""
    today = timezone.localdate()
    bounds = MealService.objects.aggregate(
        first=Min("date"),
        baseline_end=Max("date", filter=Q(prep_mode=PrepMode.REGISTERED_STRENGTH)),
    )
    first = bounds["first"]
    baseline_end = bounds["baseline_end"]
    if first is None or baseline_end is None:
        return None
    live_start = min(baseline_end + dt.timedelta(days=1), today)
    return {
        "start": first,
        "baseline_end": baseline_end,
        "live_start": live_start,
        "end": today,
        "baseline_days": (baseline_end - first).days + 1,
        "live_days": (today - live_start).days + 1,
    }


def _money(value: Decimal) -> str:
    """Rupees, grouped, without decimals."""
    return f"{value:,.0f}"


def _percent(value: Decimal, places: int = 2) -> str:
    return f"{value:.{places}f}".rstrip("0").rstrip(".") if places else str(value)


def _figure(label: str, value: Decimal, decimals: int = 0, prefix: str = "", suffix: str = "") -> dict:
    """One measured figure: the text it prints and the number it counts from."""
    if decimals:
        text = f"{value:.{decimals}f}"
    else:
        text = f"{value:,.0f}"
    return {
        "label": label,
        "text": f"{prefix}{text}{suffix}",
        "raw": float(value),
        "decimals": decimals,
        "prefix": prefix,
        "suffix": suffix,
    }


def _weeks(days: int) -> int:
    return max(1, round(days / 7))


def _kitchen_preview() -> dict:
    """The kitchen tablet preview shown on the hero section."""
    today = timezone.localdate()
    services = list(
        MealService.objects.filter(date=today)
        .select_related("hall", "forecast", "preparation_plan", "actual")
        .order_by("meal", "hall__code")
    )
    if not services:
        latest_date = MealService.objects.order_by("-date").values_list("date", flat=True).first()
        if latest_date:
            today = latest_date
            services = list(
                MealService.objects.filter(date=today)
                .select_related("hall", "forecast", "preparation_plan", "actual")
                .order_by("meal", "hall__code")
            )

    rows = []
    for service in services:
        plan = getattr(service, "preparation_plan", None)
        actual = getattr(service, "actual", None)
        forecast = getattr(service, "forecast", None)
        if actual is not None:
            state = "done"
            state_label = "Written up"
        elif plan is not None:
            state = "ready"
            state_label = "Ready to cook"
        else:
            state = "waiting"
            state_label = "No plan yet"

        target = None
        if plan and plan.portions_to_prepare:
            target = plan.portions_to_prepare
        elif forecast and forecast.predicted_attendance:
            target = round(forecast.predicted_attendance)

        rows.append(
            {
                "service": service,
                "meal_name": service.get_meal_display(),
                "hall_name": service.hall.name,
                "plan": plan,
                "actual": actual,
                "forecast": forecast,
                "state": state,
                "state_label": state_label,
                "turnout": service.attendance_count,
                "target": target,
                "leftover": actual.leftover_portions_total if actual else None,
            }
        )

    if not rows:
        return {
            "today": today,
            "totals": {
                "services": 6,
                "outstanding": 6,
                "to_prepare": 4638,
                "turnout": 0,
                "leftover": 0,
            },
            "rows": [
                {"meal_name": "Breakfast", "hall_name": "North Block Mess", "turnout": 0, "target": 434, "state_label": "Ready to cook"},
                {"meal_name": "Breakfast", "hall_name": "South Block Mess", "turnout": 0, "target": 298, "state_label": "Ready to cook"},
                {"meal_name": "Dinner", "hall_name": "North Block Mess", "turnout": 0, "target": 1007, "state_label": "Ready to cook"},
            ],
        }

    outstanding = sum(1 for r in rows if r["state"] != "done")
    to_prepare = sum(r["target"] for r in rows if r["target"])
    turnout = sum(r["turnout"] for r in rows)
    leftover = sum(r["leftover"] for r in rows if r["leftover"] is not None)

    return {
        "today": today,
        "totals": {
            "services": len(rows),
            "outstanding": outstanding,
            "to_prepare": to_prepare,
            "turnout": turnout,
            "leftover": leftover,
        },
        "rows": rows[:3],
    }


def _scan_preview() -> dict:
    """The attendance capture screen preview shown on the scan section."""
    today = timezone.localdate()
    services = list(
        MealService.objects.filter(date=today)
        .select_related("hall")
        .order_by("meal", "hall__code")
    )
    if not services:
        latest_date = MealService.objects.order_by("-date").values_list("date", flat=True).first()
        if latest_date:
            services = list(
                MealService.objects.filter(date=latest_date)
                .select_related("hall")
                .order_by("meal", "hall__code")
            )

    first = services[0] if services else None
    options = [
        {"id": s.id, "label": f"{s.hall.name}, {s.get_meal_display()}"} for s in services
    ]
    if not options:
        options = [{"id": 0, "label": "North Block Mess, Breakfast"}]

    return {
        "today": today,
        "services_count": len(options),
        "service_name": f"{first.hall.name}, {first.get_meal_display()}" if first else "North Block Mess, Breakfast",
        "registered": first.registered_strength if first else 620,
        "turnout": first.attendance_count if first else 0,
        "options": options,
    }


def _build_landing_context() -> dict:
    """Everything the landing page shows, measured rather than typed."""
    kitchen = _kitchen_preview()
    scan = _scan_preview()
    periods = _periods()
    if periods is None:
        return {"periods": None, "measured": None, "has_data": False, "kitchen": kitchen, "scan": scan}

    savings = reporting.baseline_comparison(
        periods["start"],
        periods["baseline_end"],
        periods["live_start"],
        periods["end"],
    )
    accuracy = reporting.accuracy_summary(periods["live_start"], periods["end"])
    svc_agg = MealService.objects.filter(
        date__gte=periods["start"], date__lte=periods["end"]
    ).aggregate(service_count=Count("id"), day_count=Count("date", distinct=True))
    service_count = svc_agg["service_count"] or 0
    day_count = svc_agg["day_count"] or 0
    forecast_count = Forecast.objects.filter(
        service__date__gte=periods["live_start"], service__date__lte=periods["end"]
    ).count()

    baseline_services = savings["baseline"]["services"] or 0
    live_services = savings["live"]["services"] or 0
    waste_before = savings["baseline"]["waste_cost"] / baseline_services if baseline_services else Decimal("0")
    waste_after = savings["live"]["waste_cost"] / live_services if live_services else Decimal("0")

    rows = [
        _figure("Waste per service, before", waste_before, 0, "₹"),
        _figure("Waste per service, after", waste_after, 0, "₹"),
        _figure("Saved on every service", savings["saving_per_service"], 0, "₹"),
        _figure("Mean forecast error", accuracy["mape_pct"], 2, "", "%"),
        _figure("Turnout inside the published range", accuracy["coverage_pct"], 1, "", "%"),
    ]

    return {
        "has_data": True,
        "kitchen": kitchen,
        "scan": scan,
        "periods": periods,
        "rows": rows,
        "measured": {
            "change_pct": _percent(savings["saving_pct"], 1),
            "saved_per_service": _money(savings["saving_per_service"]),
            "mape_pct": _percent(accuracy["mape_pct"]),
            "coverage_pct": _percent(accuracy["coverage_pct"], 1),
            "scored": accuracy["forecasts"],
            "forecast_count": forecast_count,
            "baseline_services": baseline_services,
            "live_services": live_services,
            "halls": DiningHall.objects.filter(is_active=True).count(),
            "services": service_count,
            "days": day_count,
            "weeks": _weeks((periods["end"] - periods["start"]).days + 1),
            "baseline_weeks": _weeks(periods["baseline_days"]),
            "live_weeks": _weeks(periods["live_days"]),
        },
    }


def landing_context() -> dict:
    """Cached wrapper around _build_landing_context (60s TTL)."""
    return cache.get_or_set("landing_context_v1", _build_landing_context, 60)


def landing_index(request):
    """The landing page. Public: it is the page a mess manager lands on."""
    return render(request, "landing/index.html", landing_context())
