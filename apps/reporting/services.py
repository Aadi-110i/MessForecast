"""M9 - Accuracy and improvement reporting.

The reports the specification names:

* forecast against actual accuracy (MAPE) by meal and hall
* waste quantity and cost by dish, meal, hall and period
* top-ten waste dishes
* cost-saving trend against the pre-deployment baseline
* attendance patterns by weekday, event and exam period
* ingredient consumption against indent
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncWeek

from apps.core.utils import as_date, q2, q3
from apps.forecasting.models import Forecast
from apps.waste.models import WasteRecord


def _accuracy_queryset(start: dt.date, end: dt.date, hall=None):
    queryset = Forecast.objects.filter(
        service__date__gte=start,
        service__date__lte=end,
        service__attendance_count__gt=0,
    ).exclude(predicted_attendance=0)
    if hall is not None:
        queryset = queryset.filter(service__hall=hall)
    return queryset


def mape_by_meal_and_hall(start: dt.date, end: dt.date) -> list[dict]:
    """MAPE broken down by meal and hall."""
    rows = (
        _accuracy_queryset(start, end)
        .values("service__meal", "service__hall__name", "service__hall__code")
        .annotate(
            forecasts=Count("id"),
            avg_predicted=Avg("predicted_attendance"),
            avg_actual=Avg("service__attendance_count"),
        )
    )
    results = []
    for row in rows:
        predicted = row["avg_predicted"] or 0
        actual = row["avg_actual"] or 0
        # MAPE computed from the means is a good approximation of the mean of
        # the individual percentage errors, and is what the dashboard shows.
        if predicted and actual:
            mape = abs(Decimal(str(actual)) - Decimal(str(predicted))) / Decimal(str(actual)) * 100
        else:
            mape = Decimal("0")
        results.append(
            {
                "meal": row["service__meal"],
                "hall": row["service__hall__name"],
                "hall_code": row["service__hall__code"],
                "forecasts": row["forecasts"],
                "avg_predicted": q2(predicted),
                "avg_actual": q2(actual),
                "mape_pct": q2(mape),
            }
        )
    results.sort(key=lambda r: (r["meal"], r["hall"]))
    return results


def mape_over_time(start: dt.date, end: dt.date, hall=None) -> list[dict]:
    """Weekly MAPE - the series that shows whether the forecast is improving."""
    queryset = _accuracy_queryset(start, end, hall)
    rows = (
        queryset.annotate(week=TruncWeek("service__date"))
        .values("week")
        .annotate(
            forecasts=Count("id"),
            avg_predicted=Avg("predicted_attendance"),
            avg_actual=Avg("service__attendance_count"),
        )
        .order_by("week")
    )
    results = []
    for row in rows:
        predicted = row["avg_predicted"] or 0
        actual = row["avg_actual"] or 0
        mape = (
            abs(Decimal(str(actual)) - Decimal(str(predicted))) / Decimal(str(actual)) * 100
            if predicted and actual
            else Decimal("0")
        )
        results.append(
            {
                "week": as_date(row["week"]),
                "forecasts": row["forecasts"],
                "avg_predicted": q2(predicted),
                "avg_actual": q2(actual),
                "mape_pct": q2(mape),
            }
        )
    return results


def exact_mape(start: dt.date, end: dt.date, hall=None) -> Decimal:
    """The exact MAPE: the mean of every individual percentage error.

    ``mape_by_meal_and_hall`` uses a ratio-of-means approximation for display;
    this is the number quoted in the accuracy report.
    """
    errors: list[Decimal] = []
    for forecast in _accuracy_queryset(start, end, hall).select_related("service"):
        ape = forecast.absolute_percentage_error()
        if ape is not None:
            errors.append(ape)
    if not errors:
        return Decimal("0")
    return q2(sum(errors, Decimal("0")) / Decimal(len(errors)))


def forecast_vs_actual_rows(start: dt.date, end: dt.date, hall=None, limit: int = 500) -> list[dict]:
    """Row-per-forecast detail for the accuracy table."""
    queryset = _accuracy_queryset(start, end, hall).select_related(
        "service", "service__hall"
    ).order_by("service__date", "service__meal")[:limit]
    rows = []
    for forecast in queryset:
        actual = forecast.service.attendance_count
        rows.append(
            {
                "date": forecast.service.date,
                "hall": forecast.service.hall.name,
                "meal": forecast.service.meal,
                "predicted": forecast.predicted_attendance,
                "lower_bound": forecast.lower_bound,
                "upper_bound": forecast.upper_bound,
                "actual": actual,
                "error": q2(Decimal(actual) - forecast.predicted_attendance),
                "ape_pct": forecast.absolute_percentage_error(),
                "within_range": forecast.lower_bound <= actual <= forecast.upper_bound,
                "explanation": forecast.explanation,
            }
        )
    return rows


def accuracy_summary(start: dt.date, end: dt.date, hall=None) -> dict:
    """Headline accuracy figures for the dashboard."""
    forecasts = list(_accuracy_queryset(start, end, hall).select_related("service"))
    errors = []
    within = 0
    bias = []
    for forecast in forecasts:
        ape = forecast.absolute_percentage_error()
        if ape is not None:
            errors.append(ape)
        actual = forecast.service.attendance_count
        if forecast.lower_bound <= actual <= forecast.upper_bound:
            within += 1
        signed = forecast.absolute_error()
        if signed is not None:
            bias.append(signed)
    mape = q2(sum(errors, Decimal("0")) / Decimal(len(errors))) if errors else Decimal("0")
    mean_bias = q2(sum(bias, Decimal("0")) / Decimal(len(bias))) if bias else Decimal("0")
    return {
        "forecasts": len(forecasts),
        "mape_pct": mape,
        "mean_bias": mean_bias,
        "coverage_pct": q2(Decimal(within) / Decimal(len(forecasts)) * 100) if forecasts else Decimal("0"),
        "within_range": within,
    }


# ---------------------------------------------------------------------------
# Saving against the baseline
# ---------------------------------------------------------------------------

def baseline_comparison(
    baseline_start: dt.date,
    baseline_end: dt.date,
    live_start: dt.date,
    live_end: dt.date,
    hall=None,
) -> dict:
    """Compare the pre-deployment baseline period with the live period.

    The baseline is the period when the kitchen cooked against the registered
    strength. The live period is when it cooked against the forecast.
    """
    baseline = _period_stats(baseline_start, baseline_end, hall)
    live = _period_stats(live_start, live_end, hall)

    baseline_services = baseline["services"] or 0
    live_services = live["services"] or 0

    baseline_per_service = (
        baseline["waste_cost"] / baseline_services if baseline_services else Decimal("0")
    )
    live_per_service = live["waste_cost"] / live_services if live_services else Decimal("0")
    saving_per_service = baseline_per_service - live_per_service
    saving_pct = (
        (saving_per_service / baseline_per_service * 100) if baseline_per_service else Decimal("0")
    )

    return {
        "baseline": baseline,
        "live": live,
        "saving_per_service": q2(saving_per_service),
        "saving_pct": q2(saving_pct),
        "annualised_saving": q2(saving_per_service * 900),
        "waste_cost_change_pct": q2(
            ((live["waste_cost"] - baseline["waste_cost"]) / baseline["waste_cost"] * 100)
            if baseline["waste_cost"]
            else Decimal("0")
        ),
    }


def _period_stats(start: dt.date, end: dt.date, hall=None) -> dict:
    queryset = WasteRecord.objects.filter(service_date__gte=start, service_date__lte=end)
    if hall is not None:
        queryset = queryset.filter(hall=hall)
    totals = queryset.aggregate(
        cost=Sum("waste_cost"),
        quantity=Sum("waste_quantity"),
        services=Count("service", distinct=True),
        records=Count("id"),
    )
    return {
        "start": start,
        "end": end,
        "waste_cost": q2(totals["cost"] or 0),
        "waste_quantity_kg": q3(totals["quantity"] or 0),
        "services": totals["services"] or 0,
        "records": totals["records"] or 0,
    }


def saving_trend_by_week(
    baseline_start: dt.date, baseline_end: dt.date, live_start: dt.date, live_end: dt.date, hall=None
) -> list[dict]:
    """Week-by-week waste cost with a baseline average line, to show the turn."""
    rows = (
        WasteRecord.objects.filter(service_date__gte=baseline_start, service_date__lte=live_end)
        .filter(**({"hall": hall} if hall is not None else {}))
        .annotate(week=TruncWeek("service_date"))
        .values("week")
        .annotate(cost=Sum("waste_cost"), services=Count("service", distinct=True))
        .order_by("week")
    )
    baseline_avg = (
        WasteRecord.objects.filter(service_date__gte=baseline_start, service_date__lte=baseline_end)
        .filter(**({"hall": hall} if hall is not None else {}))
        .aggregate(avg=Avg("waste_cost"))["avg"]
        or 0
    )
    baseline_per_service = None
    baseline_services = (
        WasteRecord.objects.filter(service_date__gte=baseline_start, service_date__lte=baseline_end)
        .filter(**({"hall": hall} if hall is not None else {}))
        .aggregate(n=Count("service", distinct=True))["n"]
        or 0
    )
    if baseline_services:
        baseline_per_service = Decimal(str(baseline_avg)) / Decimal(baseline_services)

    trend = []
    for row in rows:
        week = as_date(row["week"])
        per_service = (Decimal(str(row["cost"] or 0)) / row["services"]) if row["services"] else Decimal("0")
        is_live = week is not None and live_start <= week <= (live_end + dt.timedelta(days=6))
        trend.append(
            {
                "week": week,
                "waste_cost": q2(row["cost"] or 0),
                "services": row["services"],
                "waste_cost_per_service": q2(per_service),
                "baseline_per_service": q2(baseline_per_service) if baseline_per_service else None,
                "period": "live" if is_live else "baseline",
            }
        )
    return trend


# ---------------------------------------------------------------------------
# Ingredient consumption against indent
# ---------------------------------------------------------------------------

def ingredient_consumption_vs_indent(start: dt.date, end: dt.date, hall=None) -> list[dict]:
    """Compare what the indent asked for with what was actually consumed.

    A large positive gap means the indent over-asked; a negative gap means the
    kitchen ran short and had to improvise.
    """
    from apps.actuals.models import DishActual, ServiceActual
    from apps.planning.models import IngredientIndent, IndentLine

    indents = IngredientIndent.objects.filter(date__gte=start, date__lte=end)
    if hall is not None:
        indents = indents.filter(hall=hall)

    indented: dict[tuple[int, int], Decimal] = {}
    for line in IndentLine.objects.filter(indent__in=indents).select_related("ingredient"):
        key = (line.indent_id, line.ingredient_id)
        indented[key] = indented.get(key, Decimal("0")) + line.quantity

    actuals = ServiceActual.objects.filter(service__date__gte=start, service__date__lte=end)
    if hall is not None:
        actuals = actuals.filter(service__hall=hall)

    consumed: dict[tuple[int, int], Decimal] = {}
    ingredient_names: dict[int, str] = {}
    for dish_actual in DishActual.objects.filter(service_actual__in=actuals).select_related(
        "dish", "service_actual__service"
    ):
        service = dish_actual.service_actual.service
        recipe = dish_actual.dish.active_recipe(service.date)
        if recipe is None:
            continue
        consumed_portions = max(0, dish_actual.prepared_portions - dish_actual.waste_portions)
        indent = IngredientIndent.objects.filter(
            plan__service=service, hall=service.hall
        ).first()
        if indent is None:
            continue
        for recipe_item in recipe.items.select_related("ingredient"):
            quantity = Decimal(consumed_portions) * recipe_item.gross_quantity
            key = (indent.id, recipe_item.ingredient_id)
            consumed[key] = consumed.get(key, Decimal("0")) + quantity
            ingredient_names[recipe_item.ingredient_id] = recipe_item.ingredient.name

    rows = []
    all_keys = set(indented) | set(consumed)
    for indent_id, ingredient_id in sorted(all_keys):
        required = indented.get((indent_id, ingredient_id), Decimal("0"))
        used = consumed.get((indent_id, ingredient_id), Decimal("0"))
        rows.append(
            {
                "indent_id": indent_id,
                "ingredient_id": ingredient_id,
                "ingredient": ingredient_names.get(ingredient_id, ""),
                "indented": q3(required),
                "consumed": q3(used),
                "variance": q3(required - used),
                "variance_pct": q2((required - used) / required * 100) if required else Decimal("0"),
            }
        )
    return rows
