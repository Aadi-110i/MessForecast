"""Recipe management screens.

The dish list and the recipe behind each dish: the ingredients, the trim
loss, the portion cost and where the dish is served. The rules live in
``apps.catalog.services``.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.permissions import has_capability
from apps.catalog import services as catalog_services
from apps.catalog.models import Dish, Ingredient


def _forbidden():
    return JsonResponse({"detail": "Not permitted"}, status=403)


@login_required
@require_GET
def recipe_console(request):
    """The recipe console: every dish, its active recipe and its cost."""
    if not has_capability(request.user, "VIEW_MENU"):
        return _forbidden()

    today = dt.date.today()
    dishes = catalog_services.active_dishes(today)
    costs = catalog_services.dish_costs(dishes, today)

    rows = []
    for dish in dishes:
        recipe = getattr(dish, "_active_recipe", None)
        cost = costs.get(dish.pk, {})
        usage = catalog_services.menu_usage(dish)
        rows.append(
            {
                "dish": dish,
                "recipe": recipe,
                "cost": cost.get("portion_cost_with_trim", 0),
                "cost_net": cost.get("portion_cost", 0),
                "line_count": len(cost.get("lines", [])),
                "usage": usage,
            }
        )

    context = {
        "today": today,
        "rows": rows,
        "dishes": dishes,
        "ingredients": Ingredient.objects.filter(is_active=True).order_by("name"),
        "total_dishes": len(rows),
        "unversioned": [r for r in rows if r["recipe"] is None],
        "figures": [
            {
                "label": "Dishes",
                "value": len(rows),
                "note": f"{len(dishes) - len([r for r in rows if r['recipe'] is None])} with a recipe in force",
            },
            {
                "label": "Cheapest portion",
                "value": f"₹{min((r['cost'] for r in rows if r['cost']), default=0):.2f}",
                "note": "At current ingredient prices",
            },
            {
                "label": "Dearest portion",
                "value": f"₹{max((r['cost'] for r in rows if r['cost']), default=0):.2f}",
                "note": "At current ingredient prices",
            },
            {
                "label": "Average portion",
                "value": f"₹{(sum(r['cost'] for r in rows) / len(rows)):.2f}" if rows else "₹0.00",
                "note": "Across every dish with a recipe",
            },
        ],
    }
    return render(request, "console/recipes.html", context)


@login_required
@require_GET
def recipe_detail(request, dish_id: int):
    """One dish: its recipe versions, the lines of each, and the cost."""
    if not has_capability(request.user, "VIEW_MENU"):
        return _forbidden()

    dish = get_object_or_404(Dish, pk=dish_id)
    today = dt.date.today()
    versions = catalog_services.recipe_versions(dish)
    costs = catalog_services.cost_map_for(Ingredient.objects.filter(is_active=True), today)

    version_costs = []
    for version in versions:
        detail = catalog_services.recipe_cost(version, costs)
        version_costs.append({"recipe": version, **detail})

    active = next(
        (v for v in version_costs if v["recipe"].effective_from <= today
         and (v["recipe"].effective_to is None or v["recipe"].effective_to >= today)),
        version_costs[0] if version_costs else None,
    )

    context = {
        "dish": dish,
        "versions": version_costs,
        "active": active,
        "usage": catalog_services.menu_usage(dish),
        "ingredients": Ingredient.objects.filter(is_active=True).order_by("name"),
        "ingredient_rows": list(range(6)),
        "today": today,
        "next_version": catalog_services.next_version(dish),
        "dish_specs": [
            {"name": "Code", "value": dish.code},
            {"name": "Category", "value": dish.get_category_display()},
            {"name": "Serving size", "value": f"{dish.serving_size_g:f} g"},
            {"name": "Versions", "value": len(version_costs)},
        ],
    }
    return render(request, "console/recipe_detail.html", context)


@login_required
@require_POST
def recipe_create_version(request, dish_id: int):
    """Create a new version of a dish's recipe."""
    if not has_capability(request.user, "MANAGE_MASTERS"):
        return _forbidden()

    dish = get_object_or_404(Dish, pk=dish_id)
    today = dt.date.today()

    lines = []
    ingredient_ids = request.POST.getlist("line_ingredient")
    quantities = request.POST.getlist("line_quantity")
    trims = request.POST.getlist("line_trim")

    for index, raw_id in enumerate(ingredient_ids):
        if not raw_id:
            continue
        quantity = quantities[index] if index < len(quantities) else ""
        trim = trims[index] if index < len(trims) else "0"
        if not quantity:
            continue
        try:
            lines.append(
                {
                    "ingredient_id": int(raw_id),
                    "quantity": quantity,
                    "trim_loss_pct": trim or 0,
                }
            )
        except (TypeError, ValueError):
            continue

    if not lines:
        return JsonResponse(
            {"detail": "A recipe needs at least one ingredient line"}, status=400
        )

    notes = (request.POST.get("notes") or "").strip()
    recipe = catalog_services.create_version(dish, lines, today, notes)
    return JsonResponse({"ok": True, "id": recipe.id, "version": recipe.version})


# ---------------------------------------------------------------------------
# Dish management
# ---------------------------------------------------------------------------


#: The long category labels read well in a form and badly in a table, so the
#: table gets the short form of the same word.
CATEGORY_SHORT = {
    "STAPLE": "Staple",
    "VEG": "Vegetable",
    "NONVEG": "Non-vegetable",
    "DAAL": "Daal",
    "SALAD": "Salad",
    "BEVERAGE": "Beverage",
    "SWEET": "Sweet",
}


def _dish_rows():
    """Every dish, with the counts that decide whether it can be deleted."""
    rows = []
    for dish in Dish.objects.all().order_by("name"):
        references = catalog_services.dish_references(dish)
        rows.append(
            {
                "dish": dish,
                "category": CATEGORY_SHORT.get(dish.category, dish.get_category_display()),
                "references": references,
                "in_use": any(references.values()),
                "total": sum(references.values()),
            }
        )
    return rows


def _dish_page(request, editing=None, errors=None, values=None, form_error=""):
    """Render the dish catalogue, with a form for a new dish or for the one
    being edited."""
    rows = _dish_rows()
    active = [r for r in rows if r["dish"].is_active]
    retired = [r for r in rows if not r["dish"].is_active]

    context = {
        "today": dt.date.today(),
        "rows": rows,
        "active": active,
        "retired": retired,
        "editing": editing,
        "errors": errors or {},
        "values": values or {},
        "form_error": form_error,
        "category_choices": Dish.Category.choices,
        "figures": [
            {"label": "Dishes", "value": len(active), "note": "On the menus today"},
            {
                "label": "Retired",
                "value": len(retired),
                "note": "Kept for the history, off the menus",
            },
            {
                "label": "Still in use",
                "value": len([r for r in active if r["in_use"]]),
                "note": "Cooked at least once, so they cannot be deleted",
            },
            {
                "label": "Categories",
                "value": len({r["dish"].category for r in active}),
                "note": "Ways the kitchen sorts what it cooks",
            },
        ],
    }
    return render(request, "console/dishes.html", context)


@login_required
@require_GET
def dish_console(request):
    """The dish catalogue: what the kitchen can cook.

    Editing the masters is a mess office job, so this screen is closed to
    everyone else. It is the one place a dish is added, corrected or retired.
    """
    if not has_capability(request.user, "MANAGE_MASTERS"):
        return _forbidden()

    return _dish_page(request)


def _dish_form_fields(request):
    """Read and validate the dish form."""
    name = (request.POST.get("name") or "").strip()
    code = (request.POST.get("code") or "").strip().upper()
    category = request.POST.get("category") or Dish.Category.VEG.value
    serving_size = (request.POST.get("serving_size_g") or "").strip()
    unit_cost = (request.POST.get("direct_unit_cost") or "").strip()

    errors = {}
    if not name:
        errors["name"] = "A dish needs a name."
    if not code:
        errors["code"] = "A dish needs a code."
    if category not in {c.value for c in Dish.Category}:
        errors["category"] = "That category is not one this kitchen cooks."

    try:
        serving = Decimal(serving_size) if serving_size else Decimal("200")
        if serving <= 0:
            errors["serving_size_g"] = "A portion weighs more than nothing."
    except (TypeError, ValueError, ArithmeticError):
        errors["serving_size_g"] = "The portion size could not be read."
        serving = None

    cost = None
    if unit_cost:
        try:
            cost = Decimal(unit_cost)
            if cost < 0:
                errors["direct_unit_cost"] = "A cost cannot be negative."
        except (TypeError, ValueError, ArithmeticError):
            errors["direct_unit_cost"] = "The cost could not be read."

    return {
        "name": name,
        "code": code,
        "category": category,
        "serving_size_g": serving,
        "direct_unit_cost": cost,
        "errors": errors,
    }


@login_required
@require_POST
def dish_create(request):
    """Add a dish."""
    if not has_capability(request.user, "MANAGE_MASTERS"):
        return _forbidden()

    fields = _dish_form_fields(request)
    if fields["errors"]:
        return _dish_page(request, errors=fields["errors"], values={
            "name": fields["name"],
            "code": fields["code"],
            "category": fields["category"],
        })

    if Dish.objects.filter(code=fields["code"]).exists():
        return _dish_page(
            request,
            errors={"code": "A dish already carries that code."},
            values={"name": fields["name"], "code": fields["code"], "category": fields["category"]},
        )

    dish = catalog_services.create_dish(
        name=fields["name"],
        code=fields["code"],
        category=fields["category"],
        serving_size_g=fields["serving_size_g"],
        direct_unit_cost=fields["direct_unit_cost"],
    )
    return redirect("console-dishes")


@login_required
def dish_update(request, dish_id: int):
    """Edit a dish.

    The same screen serves the form and the save, so a correction is one
    page rather than two, and the form is there whether or not JavaScript
    runs.
    """
    if not has_capability(request.user, "MANAGE_MASTERS"):
        return _forbidden()

    dish = get_object_or_404(Dish, pk=dish_id)

    if request.method == "GET":
        return _dish_page(
            request,
            editing=dish,
            values={
                "name": dish.name,
                "code": dish.code,
                "category": dish.category,
                "serving_size_g": f"{dish.serving_size_g:f}",
                "direct_unit_cost": "" if dish.direct_unit_cost is None else f"{dish.direct_unit_cost:f}",
            },
        )

    fields = _dish_form_fields(request)
    if fields["errors"]:
        return _dish_page(
            request,
            editing=dish,
            errors=fields["errors"],
            values={
                "name": fields["name"],
                "code": fields["code"],
                "category": fields["category"],
                "serving_size_g": "" if fields["serving_size_g"] is None else f"{fields['serving_size_g']:f}",
                "direct_unit_cost": "" if fields["direct_unit_cost"] is None else f"{fields['direct_unit_cost']:f}",
            },
        )

    clash = Dish.objects.filter(code=fields["code"]).exclude(pk=dish.pk)
    if clash.exists():
        return _dish_page(
            request,
            editing=dish,
            errors={"code": "Another dish already carries that code."},
            values={"name": fields["name"], "code": fields["code"], "category": fields["category"]},
        )

    catalog_services.update_dish(
        dish,
        name=fields["name"],
        code=fields["code"],
        category=fields["category"],
        serving_size_g=fields["serving_size_g"],
        direct_unit_cost=fields["direct_unit_cost"],
    )
    return redirect("console-dishes")


@login_required
@require_POST
def dish_delete(request, dish_id: int):
    """Delete a dish, or say why it cannot be deleted.

    A dish that has been cooked keeps the history that mentions it, so it is
    retired rather than deleted. Retiring takes it off the menus and keeps
    the record, which is what the kitchen actually wants when it stops
    cooking something.
    """
    if not has_capability(request.user, "MANAGE_MASTERS"):
        return _forbidden()

    dish = get_object_or_404(Dish, pk=dish_id)

    if request.POST.get("action") == "retire":
        catalog_services.retire_dish(dish)
        return redirect("console-dishes")

    deleted, references = catalog_services.delete_dish(dish)
    if not deleted:
        holding = [
            f"{count} {label}"
            for label, count in (
                ("on a menu", references["menus"]),
                ("in a preparation plan", references["plans"]),
                ("in a recorded actual", references["actuals"]),
                ("in a waste record", references["waste"]),
            )
            if count
        ]
        return _dish_page(
            request,
            form_error=(
                f"{dish.name} has been cooked, so it cannot be deleted. "
                f"It is still {' and '.join(holding)}. "
                "Retire it instead: that takes it off the menus and keeps the history."
            ),
        )

    return redirect("console-dishes")
