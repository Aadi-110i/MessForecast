"""Recipe management: the dishes, their versioned recipes, and what they cost.

A recipe is versioned rather than edited. When the kitchen changes the
proportion of rice in a dish, that is a new version of the recipe, and the
old version stays because the cost of a dish served in March has to be
recomputable later.

The cost of a portion is rolled up from the ingredient lines:

    gross quantity  = quantity / (1 - trim loss)
    line cost       = gross quantity x unit cost
    portion cost    = line cost summed over the recipe

Trim loss is why the two costs exist. Buying 1 kg of onion yields less than
1 kg of usable onion, and the difference is waste that the platform
already measures elsewhere.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import Count, Q

from apps.catalog.models import CostRate, Dish, Recipe, RecipeItem
from apps.core.constants import MealType


def active_dishes(on_date: dt.date | None = None) -> list[Dish]:
    """Every active dish with its active recipe annotated."""
    on_date = on_date or dt.date.today()
    dishes = list(Dish.objects.filter(is_active=True).order_by("category", "name"))
    recipes = active_recipes_for(dishes, on_date)
    for dish in dishes:
        dish._active_recipe = recipes.get(dish.pk)
    return dishes


def active_recipes_for(dishes, on_date: dt.date | None = None) -> dict:
    """Map dish id to the recipe in force on ``on_date``.

    The most recent version whose window covers the date wins. A dish with
    no covering version is absent from the mapping, which is different from
    a dish with a version that has no lines.
    """
    on_date = on_date or dt.date.today()
    dish_ids = [d.pk if hasattr(d, "pk") else d for d in dishes]
    recipes = (
        Recipe.objects.filter(dish_id__in=dish_ids)
        .filter(Q(effective_from__lte=on_date))
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
        .order_by("dish_id", "-version")
    )
    chosen: dict[int, Recipe] = {}
    for recipe in recipes:
        chosen.setdefault(recipe.dish_id, recipe)
    return chosen


def recipe_versions(dish: Dish) -> list[Recipe]:
    """Every version of a dish's recipe, newest first."""
    return list(
        Recipe.objects.filter(dish=dish)
        .annotate(line_count=Count("items"))
        .order_by("-version")
    )


def recipe_cost(recipe: Recipe | None, costs: dict | None = None) -> dict:
    """The cost of one portion of a recipe, and how it was reached.

    Returns the portion cost, the cost including trim, and the lines that
    made it up, so the number can be argued with rather than trusted.
    """
    if recipe is None:
        return {
            "portion_cost": Decimal("0"),
            "portion_cost_with_trim": Decimal("0"),
            "lines": [],
            "grams": Decimal("0"),
        }

    costs = costs or {}
    lines = []
    portion_total = Decimal("0")
    portion_total_trim = Decimal("0")
    grams = Decimal("0")

    for item in recipe.items.select_related("ingredient"):
        unit_cost = costs.get(item.ingredient_id, Decimal("0"))
        gross = item.gross_quantity or Decimal("0")
        line_cost = gross * unit_cost
        net_cost = item.quantity * unit_cost
        grams += (gross * Decimal("1000")) if item.ingredient.base_unit == "kg" else Decimal("0")
        portion_total += net_cost
        portion_total_trim += line_cost
        lines.append(
            {
                "item": item,
                "ingredient": item.ingredient,
                "quantity": item.quantity,
                "gross": gross,
                "unit_cost": unit_cost,
                "cost": net_cost,
                "cost_with_trim": line_cost,
            }
        )

    return {
        "portion_cost": portion_total,
        "portion_cost_with_trim": portion_total_trim,
        "lines": lines,
        "grams": grams,
    }


def cost_map_for(ingredients, on_date: dt.date | None = None, hall=None) -> dict:
    """Ingredient id to unit cost, taken from the rates in force."""
    on_date = on_date or dt.date.today()
    rates = CostRate.objects.filter(effective_from__lte=on_date).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=on_date)
    )
    if hall is not None:
        hall_rates = rates.filter(hall=hall)
        global_rates = rates.filter(hall__isnull=True)
        chosen: dict[int, Decimal] = {}
        for rate in global_rates.order_by("-effective_from"):
            chosen.setdefault(rate.ingredient_id, rate.unit_cost)
        for rate in hall_rates.order_by("-effective_from"):
            chosen[rate.ingredient_id] = rate.unit_cost
        return chosen

    chosen = {}
    for rate in rates.order_by("-effective_from"):
        chosen.setdefault(rate.ingredient_id, rate.unit_cost)
    return chosen


def dish_costs(dishes, on_date: dt.date | None = None, hall=None) -> dict:
    """Portion cost for every dish, keyed by dish id."""
    on_date = on_date or dt.date.today()
    recipes = active_recipes_for(dishes, on_date)
    ingredient_ids = set()
    for recipe in recipes.values():
        ingredient_ids.update(
            recipe.items.values_list("ingredient_id", flat=True)
        )
    from apps.catalog.models import Ingredient

    ingredients = Ingredient.objects.filter(pk__in=ingredient_ids)
    costs = cost_map_for(ingredients, on_date, hall)

    result = {}
    for dish in dishes:
        recipe = recipes.get(dish.pk)
        result[dish.pk] = recipe_cost(recipe, costs)
    return result


def menu_usage(dish: Dish) -> dict:
    """Where a dish is served, so a recipe change can be weighed."""
    from apps.menu.models import MenuItem

    items = MenuItem.objects.filter(dish=dish).select_related("menu")
    menus = sorted({item.menu.name for item in items})
    meals = sorted({item.meal for item in items}, key=lambda m: MealType(m).label if m in {x.value for x in MealType} else m)
    return {"menus": menus, "meals": meals, "count": items.count()}


def next_version(dish: Dish) -> int:
    """The version number a new recipe for this dish should carry."""
    latest = Recipe.objects.filter(dish=dish).order_by("-version").first()
    return (latest.version + 1) if latest else 1


# ---------------------------------------------------------------------------
# Dishes
# ---------------------------------------------------------------------------


def dish_references(dish: Dish) -> dict:
    """What still holds a dish, so a refusal can say what holds it.

    A dish that has been cooked cannot be deleted, because the preparation
    plans, the actuals and the waste records that mention it are the history
    of what the kitchen did. It can be retired, which takes it off the menus
    and keeps the history.
    """
    from apps.actuals.models import DishActual
    from apps.menu.models import MenuItem
    from apps.planning.models import PreparationLine
    from apps.waste.models import WasteRecord

    return {
        "menus": MenuItem.objects.filter(dish=dish).count(),
        "plans": PreparationLine.objects.filter(dish=dish).count(),
        "actuals": DishActual.objects.filter(dish=dish).count(),
        "waste": WasteRecord.objects.filter(dish=dish).count(),
    }


def create_dish(
    name: str,
    code: str,
    category: str,
    serving_size_g,
    direct_unit_cost=None,
) -> Dish:
    """Add a dish to the catalogue."""
    return Dish.objects.create(
        name=name.strip(),
        code=code.strip().upper(),
        category=category,
        serving_size_g=serving_size_g,
        direct_unit_cost=direct_unit_cost,
    )


def update_dish(dish: Dish, **fields) -> Dish:
    """Edit a dish in place.

    The name, the code and the category may change. The portion size may
    change, but the history of what a portion weighed is in the actuals and
    the waste records, and those are not rewritten.
    """
    for field in ("name", "code", "category", "serving_size_g", "direct_unit_cost"):
        if field in fields:
            value = fields[field]
            if field in ("name", "code"):
                value = value.strip()
                if field == "code":
                    value = value.upper()
            setattr(dish, field, value)
    dish.save()
    return dish


def delete_dish(dish: Dish) -> tuple[bool, dict]:
    """Delete a dish, if the history allows it.

    Returns ``(deleted, references)``. A dish that has never been cooked is
    deleted outright. One that has been cooked is refused, and the counts say
    what is holding it, because the caller should offer to retire it rather
    than lose the record.
    """
    references = dish_references(dish)
    if any(references.values()):
        return False, references
    dish.delete()
    return True, references


def retire_dish(dish: Dish) -> Dish:
    """Take a dish off the menus without losing its history."""
    dish.is_active = False
    dish.save(update_fields=["is_active", "updated_at"])
    return dish


def create_version(
    dish: Dish,
    lines: list[dict],
    on_date: dt.date | None = None,
    notes: str = "",
) -> Recipe:
    """Create a new version of a dish's recipe and close the old one."""
    on_date = on_date or dt.date.today()
    previous = (
        Recipe.objects.filter(dish=dish, effective_to__isnull=True)
        .order_by("-version")
        .first()
    )
    if previous is not None:
        previous.effective_to = on_date - dt.timedelta(days=1)
        previous.save(update_fields=["effective_to", "updated_at"])

    recipe = Recipe.objects.create(
        dish=dish,
        version=next_version(dish),
        effective_from=on_date,
        notes=notes,
    )
    for line in lines:
        RecipeItem.objects.create(
            recipe=recipe,
            ingredient_id=line["ingredient_id"],
            quantity=Decimal(str(line.get("quantity", 0))),
            trim_loss_pct=Decimal(str(line.get("trim_loss_pct", 0))),
        )
    return recipe
