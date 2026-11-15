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
    first = MealService.objects.order_by("date").values_list("date", flat=True).first()
    if first is None:
        return None
    baseline_end = (
        MealService.objects.filter(prep_mode=PrepMode.REGISTERED_STRENGTH)
        .order_by("-date")
        .values_list("date", flat=True)
        .first()
    )
    if baseline_end is None:
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


def landing_context() -> dict:
    """Everything the landing page shows, measured rather than typed."""
    periods = _periods()
    if periods is None:
        return {"periods": None, "measured": None, "has_data": False}

    savings = reporting.baseline_comparison(
        periods["start"],
        periods["baseline_end"],
        periods["live_start"],
        periods["end"],
    )
    accuracy = reporting.accuracy_summary(periods["live_start"], periods["end"])
    services = MealService.objects.filter(
        date__gte=periods["start"], date__lte=periods["end"]
    )
    service_count = services.count()
    day_count = services.values("date").distinct().count()
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


def landing_index(request):
    """The landing page. Public: it is the page a mess manager lands on."""
    return render(request, "landing/index.html", landing_context())
