"""M6 - Turning a forecast into a preparation quantity and an ingredient indent.

The arithmetic has to be explainable to a cook:

    portions to prepare  = forecast x (1 + acceptable over-preparation %)
    portions per dish    = portions to prepare split by what students actually eat
    ingredient required  = portions per dish x recipe quantity x (1 + trim loss)
    money                = ingredient quantity x current unit cost

The split across dishes uses the largest-remainder method so the parts always
add back to the whole - no portion is invented or lost in rounding.
"""

from __future__ import annotations

import datetime as dt
import math
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Dish, active_recipes_for, cost_map, recipe_items_for
from apps.core.utils import largest_remainder, q2, q3
from apps.events.models import ServiceLevelConfig
from apps.forecasting.models import Forecast
from apps.menu.models import MenuSchedule
from apps.planning.models import IndentLine, IngredientIndent, PreparationLine, PreparationPlan


class PlanningError(Exception):
    """Raised when a preparation plan cannot be produced."""


def _menu_for_service(service) -> tuple[MenuSchedule | None, list]:
    """The menu scheduled for this hall/date/meal and its dishes."""
    schedule = (
        MenuSchedule.objects.filter(
            hall=service.hall, date=service.date, meal=service.meal
        )
        .select_related("menu")
        .first()
    )
    if schedule is None:
        return None, []
    items = list(schedule.menu.items_for_meal(service.meal).select_related("dish"))
    return schedule, items


def _dish_shares(items) -> list[Decimal]:
    """Expected share of each dish, falling back to an even split.

    ``expected_share`` is learned from history. Until it has been learned, an
    even split is the honest assumption: we do not know that students prefer
    the curry over the rice.
    """
    if not items:
        return []
    known = [item.expected_share for item in items]
    if sum(known) > 0:
        total = sum(known)
        return [share / total for share in known]
    even = Decimal("1") / Decimal(len(items))
    return [even] * len(items)


@transaction.atomic
def generate_preparation_plan(
    service,
    forecast: Forecast | None = None,
    service_level: ServiceLevelConfig | None = None,
    persist: bool = True,
    shares: list | None = None,
) -> PreparationPlan:
    """Build (or rebuild) the preparation plan for one meal service.

    ``shares`` optionally overrides the learned dish shares, which lets a
    caller work with a running estimate of what students will take without
    writing it back to the menu first.
    """
    forecast = forecast or getattr(service, "forecast", None)
    if forecast is None:
        raise PlanningError(
            "No forecast exists for this service. Run the forecast first so the "
            "preparation is driven by a number rather than by guesswork."
        )

    schedule, items = _menu_for_service(service)
    if not items:
        raise PlanningError(
            f"No menu is scheduled for {service.hall.name} on {service.date} for "
            f"{service.get_meal_display()}, so there is nothing to prepare."
        )

    if service_level is None:
        service_level = ServiceLevelConfig.resolve(service.hall, service.meal, service.date)

    target = Decimal(forecast.predicted_attendance)
    margin_pct = Decimal(service_level.acceptable_overprep_pct)
    max_pct = Decimal(service_level.max_overprep_pct)

    # Students become portions: a student at lunch takes rice, a dal and a
    # curry, so the kitchen cooks more portions than there are students.
    portions_per_student = Decimal(service_level.portions_per_student or Decimal("1"))
    portions_target = target * portions_per_student

    portions = int(math.ceil(portions_target * (1 + margin_pct / Decimal("100"))))
    # Respect the hard ceiling the hall has configured.
    capped = int(math.ceil(portions_target * (1 + max_pct / Decimal("100"))))
    portions = min(portions, capped)
    portions = max(portions, int(portions_target))
    # The absolute buffer still applies even on a small service.
    portions = max(portions, int(portions_target) + int(service_level.min_buffer_portions))

    if shares is not None and len(shares) == len(items):
        resolved_shares = [Decimal(s) for s in shares]
    else:
        resolved_shares = _dish_shares(items)
    dish_portions = largest_remainder(Decimal(portions), resolved_shares)

    plan = PreparationPlan.objects.filter(service=service).first()
    if plan is None:
        plan = PreparationPlan(service=service)
    else:
        # A service has exactly one plan. Regenerating replaces it rather
        # than adding a second, and the kitchen is asked to acknowledge the
        # new number rather than the old one.
        plan.lines.all().delete()
        previous_indent = getattr(plan, "indent", None)
        if previous_indent is not None:
            previous_indent.delete()
        plan.status = PreparationPlan.Status.DRAFT

    plan.forecast = forecast
    plan.attendance_target = target
    plan.portions_target = q2(portions_target)
    plan.safety_margin_pct = margin_pct
    plan.portions_to_prepare = portions
    plan.over_preparation_pct = q2(
        (Decimal(portions) - portions_target) / portions_target * 100 if portions_target else Decimal("0")
    )
    plan.estimated_cost = Decimal("0")
    plan.generated_at = timezone.now()
    if persist:
        plan.save()

    # Recipes, their lines and the ingredient prices: three queries for the
    # whole menu, rather than a handful per dish.
    dishes = [item.dish for item in items]
    recipes = active_recipes_for(dishes, service.date)
    items_by_recipe = recipe_items_for(recipes.values())
    plan_ingredients = []
    for recipe in recipes.values():
        plan_ingredients.extend(line.ingredient for line in items_by_recipe.get(recipe.id, []))
    plan_costs = cost_map(plan_ingredients, service.date, service.hall)

    total_cost = Decimal("0")
    for item, share, portion_count in zip(items, resolved_shares, dish_portions):
        dish = item.dish
        unit_cost = Decimal("0")
        recipe = recipes.get(dish.id)
        if recipe is not None:
            for recipe_item in items_by_recipe.get(recipe.id, []):
                unit_cost += recipe_item.gross_quantity * plan_costs.get(recipe_item.ingredient_id, Decimal("0"))
        if dish.direct_unit_cost is not None:
            unit_cost = dish.direct_unit_cost
        line_cost = q2(Decimal(portion_count) * unit_cost)
        total_cost += line_cost
        line = PreparationLine(
            plan=plan,
            dish=dish,
            portions=portion_count,
            expected_share=q3(share),
            estimated_cost=line_cost,
        )
        if persist:
            line.save()

    plan.estimated_cost = q2(total_cost)
    plan.guidance_text = _build_guidance(service, plan, items, dish_portions)
    if persist:
        plan.save()
        _build_indent(
            plan,
            service,
            items,
            dish_portions,
            recipes=recipes,
            items_by_recipe=items_by_recipe,
            costs=plan_costs,
        )
    return plan


def _build_guidance(service, plan: PreparationPlan, items, dish_portions) -> str:
    """The brief the kitchen reads on the tablet before service."""
    forecast = plan.forecast
    lines = [
        f"{service.get_meal_display()} - {service.hall.name} - {service.date.strftime('%d %b %Y')}",
        "",
        f"Expected turnout: {int(forecast.predicted_attendance)} students "
        f"(likely between {int(forecast.lower_bound)} and {int(forecast.upper_bound)}).",
        f"Cook {plan.portions_to_prepare} portions - that is "
        f"{plan.over_preparation_pct:.1f}% above the forecast, which is the margin "
        f"this hall allows.",
        "",
        "Portions to prepare:",
    ]
    for item, portions in zip(items, dish_portions):
        lines.append(f"  - {item.dish.name}: {portions} portions")
    lines.append("")
    lines.append(f"Estimated food cost: Rs {plan.estimated_cost:,.2f}")
    if forecast and forecast.explanation:
        lines.append("")
        lines.append(forecast.explanation)
    return "\n".join(lines)


def _build_indent(plan: PreparationPlan, service, items, dish_portions, recipes=None, items_by_recipe=None, costs=None) -> IngredientIndent:
    """Aggregate recipe requirements into a procurement list."""
    indent, _ = IngredientIndent.objects.get_or_create(
        plan=plan,
        defaults={"hall": service.hall, "date": service.date},
    )
    indent.hall = service.hall
    indent.date = service.date
    indent.generated_at = timezone.now()
    indent.lines.all().delete()

    dishes = [item.dish for item in items]
    if recipes is None:
        recipes = active_recipes_for(dishes, service.date)
    if items_by_recipe is None:
        items_by_recipe = recipe_items_for(recipes.values())
    if costs is None:
        plan_ingredients = []
        for recipe in recipes.values():
            plan_ingredients.extend(line.ingredient for line in items_by_recipe.get(recipe.id, []))
        costs = cost_map(plan_ingredients, service.date, service.hall)

    totals: dict[int, dict] = {}
    for item, portions in zip(items, dish_portions):
        dish = item.dish
        recipe = recipes.get(dish.id)
        if recipe is None:
            continue
        for recipe_item in items_by_recipe.get(recipe.id, []):
            ingredient = recipe_item.ingredient
            quantity = Decimal(portions) * recipe_item.gross_quantity
            unit_cost = costs.get(recipe_item.ingredient_id, Decimal("0"))
            entry = totals.setdefault(
                ingredient.id,
                {
                    "ingredient": ingredient,
                    "quantity": Decimal("0"),
                    "unit_cost": unit_cost,
                    "sources": [],
                },
            )
            entry["quantity"] += quantity
            entry["sources"].append(f"{dish.name} ({portions})")

    total_cost = Decimal("0")
    for data in totals.values():
        ingredient = data["ingredient"]
        quantity = q3(data["quantity"])
        cost = q2(quantity * data["unit_cost"])
        total_cost += cost
        IndentLine.objects.create(
            indent=indent,
            ingredient=ingredient,
            quantity=quantity,
            unit=ingredient.base_unit,
            unit_cost=data["unit_cost"],
            estimated_cost=cost,
            source_dishes=", ".join(data["sources"])[:255],
        )

    indent.total_estimated_cost = q2(total_cost)
    indent.line_count = len(totals)
    indent.procurement_text = format_indent(indent)
    indent.save()
    return indent


def format_indent(indent: IngredientIndent) -> str:
    """Render the indent in the procurement format the kitchen already uses."""
    header = f"INDENT - {indent.hall.name} - {indent.date.strftime('%d %b %Y')}"
    rule = "=" * len(header)
    lines = [header, rule, ""]
    total = Decimal("0")
    for line in indent.lines.select_related("ingredient").all():
        total += line.estimated_cost
        lines.append(
            f"{line.ingredient.name:<28} {line.quantity:>10} {line.unit:<6} "
            f"{line.packs:>7} pack(s)   Rs {line.estimated_cost:>10,.2f}"
        )
    lines.append("")
    lines.append(f"{'TOTAL':<28} {'':>10} {'':<6} {'':>7}          Rs {total:>10,.2f}")
    return "\n".join(lines)


def indent_csv_rows(indent: IngredientIndent) -> tuple[list[str], list[list]]:
    """Header and rows for the procurement export."""
    header = [
        "Ingredient Code", "Ingredient", "Quantity", "Unit",
        "Purchase Packs", "Pack Size", "Unit Cost (Rs)", "Estimated Cost (Rs)",
        "Used In", "Hall", "Date",
    ]
    rows = []
    for line in indent.lines.select_related("ingredient").all():
        rows.append([
            line.ingredient.code,
            line.ingredient.name,
            str(line.quantity),
            line.unit,
            str(line.packs),
            str(line.ingredient.purchase_pack_size),
            str(line.unit_cost),
            str(line.estimated_cost),
            line.source_dishes,
            indent.hall.name,
            indent.date.isoformat(),
        ])
    return header, rows


def learn_dish_shares(service, lookback_days: int = 90) -> int:
    """Update ``expected_share`` for the dishes of a service's menu.

    Share is what fraction of the portions actually served went to each dish.
    This is how the system learns that, say, two thirds of students take the
    curry and only a third take the rice.

    The share is computed *per service* and then averaged, because the menu
    changes from day to day. Pooling every dish of every service into one
    total would divide by the wrong denominator: a dish that only appears on
    the days it is on the menu would be penalised for the days it is not.
    """
    from django.db.models import Sum

    from apps.actuals.models import DishActual, ServiceActual

    start = service.date - dt.timedelta(days=lookback_days)
    actuals = ServiceActual.objects.filter(
        service__hall=service.hall, service__meal=service.meal, service__date__gte=start
    ).select_related("service")

    # share[dish_id][service_id] = portions of that dish served at that service
    per_service: dict[int, dict[int, int]] = {}
    for dish_actual in DishActual.objects.filter(service_actual__in=actuals):
        per_service.setdefault(dish_actual.service_actual_id, {})[dish_actual.dish_id] = (
            dish_actual.served_portions
        )

    # Average the per-service shares per dish.
    share_sums: dict[int, Decimal] = {}
    share_counts: dict[int, int] = {}
    for served_map in per_service.values():
        total = sum(served_map.values())
        if total <= 0:
            continue
        for dish_id, served in served_map.items():
            share_sums[dish_id] = share_sums.get(dish_id, Decimal("0")) + Decimal(served) / Decimal(total)
            share_counts[dish_id] = share_counts.get(dish_id, 0) + 1

    if not share_sums:
        return 0

    updated = 0
    for item in _menu_for_service(service)[1]:
        if item.dish_id not in share_sums:
            continue
        share = share_sums[item.dish_id] / Decimal(share_counts[item.dish_id])
        if abs(item.expected_share - share) > Decimal("0.0001"):
            item.expected_share = q3(share)
            item.save(update_fields=["expected_share"])
            updated += 1
    return updated
