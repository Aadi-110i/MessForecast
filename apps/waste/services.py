"""M8 services - turning post-service actuals into measured, costed waste."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from apps.actuals.models import DishActual, ServiceActual
from apps.catalog.models import active_recipes_for, cost_map, recipe_items_for
from apps.core.constants import WasteCause
from apps.core.utils import as_date, q2, q3
from apps.waste.models import WasteRecord


class WasteError(Exception):
    """Raised when waste cannot be computed."""


def _forecast_portions_for_dishes(service, dishes, plan_lines_by_dish) -> dict:
    """Expected portions of each dish, from the plan or the forecast.

    ``plan_lines_by_dish`` is ``{dish_id: portions}`` from the preparation
    plan, already fetched.
    """
    result: dict[int, Decimal] = {}
    for dish in dishes:
        if dish.id in plan_lines_by_dish:
            result[dish.id] = Decimal(plan_lines_by_dish[dish.id])
            continue
        forecast = getattr(service, "forecast", None)
        if forecast is None:
            result[dish.id] = Decimal("0")
            continue
        # Fall back to splitting the forecast across the menu evenly.
        from apps.planning.services import _dish_shares, _menu_for_service

        _schedule, items = _menu_for_service(service)
        if not items:
            result[dish.id] = Decimal("0")
            continue
        shares = _dish_shares(items)
        total = Decimal(forecast.predicted_attendance)
        for item, share in zip(items, shares):
            if item.dish_id == dish.id:
                result[dish.id] = q2(total * share)
                break
        else:
            result[dish.id] = Decimal("0")
    return result


@transaction.atomic
def compute_waste_for_actual(service_actual: ServiceActual) -> list[WasteRecord]:
    """Create or update the waste records for one service.

    Idempotent: running it twice for the same actual gives the same rows.
    """
    service = service_actual.service
    records: list[WasteRecord] = []

    dish_actuals = list(service_actual.dish_actuals.select_related("dish"))
    if not dish_actuals:
        return records

    dishes = [dish_actual.dish for dish_actual in dish_actuals]

    # Recipes and their lines in two queries, not one per dish.
    recipes = active_recipes_for(dishes, service.date)
    items_by_recipe = recipe_items_for(recipes.values())

    # Ingredient prices in one query.
    ingredients = []
    for recipe in recipes.values():
        ingredients.extend(item.ingredient for item in items_by_recipe.get(recipe.id, []))
    costs = cost_map(ingredients, service.date, service.hall)

    # What the plan expected, in one query.
    plan = getattr(service, "preparation_plan", None)
    plan_lines_by_dish = {}
    if plan is not None:
        plan_lines_by_dish = {
            line.dish_id: line.portions
            for line in plan.lines.filter(dish_id__in=[d.id for d in dishes])
        }
    forecast_portions = _forecast_portions_for_dishes(service, dishes, plan_lines_by_dish)

    for dish_actual in dish_actuals:
        dish = dish_actual.dish
        leftover = max(0, dish_actual.prepared_portions - dish_actual.served_portions)

        # Weight of the leftover food: portions x portion size in grams.
        grams = Decimal(dish_actual.waste_portions) * (dish.serving_size_g or Decimal("0"))
        waste_quantity = q3(grams / Decimal("1000"))

        recipe = recipes.get(dish.id)
        cost_per_portion = Decimal("0")
        if recipe is not None:
            for recipe_item in items_by_recipe.get(recipe.id, []):
                unit_cost = costs.get(recipe_item.ingredient_id, Decimal("0"))
                # Gross quantity: the kitchen paid for the trim loss too.
                cost_per_portion += recipe_item.gross_quantity * unit_cost
        if dish.direct_unit_cost is not None:
            cost_per_portion = dish.direct_unit_cost
        waste_cost = q2(Decimal(dish_actual.waste_portions) * cost_per_portion)

        expected = forecast_portions.get(dish.id, Decimal("0"))
        over_prepared = q2(Decimal(dish_actual.prepared_portions) - expected)

        cause = WasteCause.OVER_PREPARATION
        if dish_actual.prepared_portions and dish_actual.served_portions > dish_actual.prepared_portions:
            cause = WasteCause.OVERSERVED

        record, _created = WasteRecord.objects.update_or_create(
            service_actual=service_actual,
            dish=dish,
            defaults={
                "service": service,
                "service_date": service.date,
                "hall": service.hall,
                "meal": service.meal,
                "leftover_portions": dish_actual.waste_portions,
                "waste_quantity": waste_quantity,
                "unit": "kg",
                "cost_per_portion": cost_per_portion,
                "waste_cost": waste_cost,
                "forecast_portions": expected,
                "over_prepared_portions": over_prepared,
                "cause": cause,
                "computed_at": timezone.now(),
            },
        )
        records.append(record)

    return records


def recompute_all_waste() -> int:
    """Recompute waste for every recorded actual. Used after a recipe or price change."""
    count = 0
    for actual in ServiceActual.objects.select_related("service"):
        compute_waste_for_actual(actual)
        count += 1
    return count


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def waste_totals(start: dt.date, end: dt.date, hall=None) -> dict:
    """Total waste quantity and cost in a period."""
    queryset = WasteRecord.objects.filter(service_date__gte=start, service_date__lte=end)
    if hall is not None:
        queryset = queryset.filter(hall=hall)
    totals = queryset.aggregate(
        cost=Sum("waste_cost"), quantity=Sum("waste_quantity"), records=Count("id")
    )
    return {
        "waste_cost": q2(totals["cost"] or 0),
        "waste_quantity_kg": q3(totals["quantity"] or 0),
        "records": totals["records"] or 0,
    }


def waste_by_week(start: dt.date, end: dt.date, hall=None) -> list[dict]:
    """Weekly waste cost trend - the chart the specification asks for."""
    from django.db.models.functions import TruncWeek

    queryset = WasteRecord.objects.filter(service_date__gte=start, service_date__lte=end)
    if hall is not None:
        queryset = queryset.filter(hall=hall)
    rows = (
        queryset.annotate(week=TruncWeek("service_date"))
        .values("week")
        .annotate(cost=Sum("waste_cost"), quantity=Sum("waste_quantity"), services=Count("service", distinct=True))
        .order_by("week")
    )
    return [
        {
            "week": as_date(row["week"]),
            "waste_cost": q2(row["cost"] or 0),
            "waste_quantity_kg": q3(row["quantity"] or 0),
            "services": row["services"],
        }
        for row in rows
    ]


def top_waste_dishes(start: dt.date, end: dt.date, hall=None, limit: int = 10) -> list[dict]:
    """The top ten dishes by wasted cost - the specification's headline report."""
    queryset = WasteRecord.objects.filter(service_date__gte=start, service_date__lte=end)
    if hall is not None:
        queryset = queryset.filter(hall=hall)
    rows = (
        queryset.values("dish__id", "dish__name", "dish__code")
        .annotate(
            waste_cost=Sum("waste_cost"),
            waste_quantity=Sum("waste_quantity"),
            portions=Sum("leftover_portions"),
            services=Count("id"),
        )
        .order_by("-waste_cost")[:limit]
    )
    return [
        {
            "dish_id": row["dish__id"],
            "dish": row["dish__name"],
            "code": row["dish__code"],
            "waste_cost": q2(row["waste_cost"] or 0),
            "waste_quantity_kg": q3(row["waste_quantity"] or 0),
            "leftover_portions": int(row["portions"] or 0),
            "services": row["services"],
        }
        for row in rows
    ]


def waste_by_meal(start: dt.date, end: dt.date, hall=None) -> list[dict]:
    queryset = WasteRecord.objects.filter(service_date__gte=start, service_date__lte=end)
    if hall is not None:
        queryset = queryset.filter(hall=hall)
    rows = (
        queryset.values("meal")
        .annotate(cost=Sum("waste_cost"), quantity=Sum("waste_quantity"), services=Count("id"))
        .order_by("meal")
    )
    return [
        {
            "meal": row["meal"],
            "waste_cost": q2(row["cost"] or 0),
            "waste_quantity_kg": q3(row["quantity"] or 0),
            "records": row["services"],
        }
        for row in rows
    ]


def waste_by_cause(start: dt.date, end: dt.date, hall=None) -> list[dict]:
    """Waste split by why it happened.

    The cause matters more than the dish. Over-preparation is a forecasting
    problem, spoilage is a storage problem, and quality rejection is a
    supplier problem, and each is fixed by a different person.
    """
    queryset = WasteRecord.objects.filter(service_date__gte=start, service_date__lte=end)
    if hall is not None:
        queryset = queryset.filter(hall=hall)
    rows = (
        queryset.values("cause")
        .annotate(
            cost=Sum("waste_cost"),
            quantity=Sum("waste_quantity"),
            portions=Sum("leftover_portions"),
            records=Count("id"),
        )
        .order_by("-cost")
    )
    return [
        {
            "cause": row["cause"],
            "label": dict(WasteCause.choices).get(row["cause"], row["cause"]),
            "waste_cost": q2(row["cost"] or 0),
            "waste_quantity_kg": q3(row["quantity"] or 0),
            "leftover_portions": int(row["portions"] or 0),
            "records": row["records"],
        }
        for row in rows
    ]


def waste_by_hall(start: dt.date, end: dt.date) -> list[dict]:
    queryset = WasteRecord.objects.filter(service_date__gte=start, service_date__lte=end)
    rows = (
        queryset.values("hall__id", "hall__name", "hall__code")
        .annotate(cost=Sum("waste_cost"), services=Count("id"))
        .order_by("-cost")
    )
    return [
        {
            "hall_id": row["hall__id"],
            "hall": row["hall__name"],
            "code": row["hall__code"],
            "waste_cost": q2(row["cost"] or 0),
            "records": row["services"],
        }
        for row in rows
    ]


def average_waste_cost_per_service(start: dt.date, end: dt.date, hall=None) -> Decimal:
    """Mean waste cost for one service - the unit the saving is measured in.

    A service has several dishes, so the total is divided by the number of
    distinct services, not by the number of waste rows.
    """
    queryset = WasteRecord.objects.filter(service_date__gte=start, service_date__lte=end)
    if hall is not None:
        queryset = queryset.filter(hall=hall)
    totals = queryset.aggregate(cost=Sum("waste_cost"), services=Count("service", distinct=True))
    services = totals["services"] or 0
    if not services:
        return Decimal("0")
    return q2(Decimal(str(totals["cost"] or 0)) / Decimal(services))
