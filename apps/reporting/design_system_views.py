"""The component catalogue.

A living reference for the component library. Every component is rendered
in every state it has, so a screen can be checked against the system
rather than against a picture of it.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.accounts.permissions import has_capability
from apps.catalog import services as catalog_services
from apps.catalog.models import DiningHall, Dish
from apps.core.constants import MealType


@login_required
@require_GET
def design_system(request):
    """Every component, in every state, with real data where it needs some."""
    if not has_capability(request.user, "VIEW_MENU"):
        return JsonResponse({"detail": "Not permitted"}, status=403)

    dishes = list(Dish.objects.filter(is_active=True).order_by("name")[:6])
    costs = catalog_services.dish_costs(dishes)

    board = {
        "days": [
            {"iso": "2026-11-09", "label": "9 Nov", "weekday": "Mon"},
            {"iso": "2026-11-10", "label": "10 Nov", "weekday": "Tue"},
            {"iso": "2026-11-11", "label": "11 Nov", "weekday": "Wed"},
            {"iso": "2026-11-12", "label": "12 Nov", "weekday": "Thu"},
            {"iso": "2026-11-13", "label": "13 Nov", "weekday": "Fri"},
            {"iso": "2026-11-14", "label": "14 Nov", "weekday": "Sat"},
            {"iso": "2026-11-15", "label": "15 Nov", "weekday": "Sun"},
        ],
        "meals": [
            {"code": "BREAKFAST", "label": "Breakfast"},
            {"code": "LUNCH", "label": "Lunch"},
            {"code": "DINNER", "label": "Dinner"},
        ],
        "cells": {
            "BREAKFAST": {
                "2026-11-09": {"menu": "Menu Cycle A", "url": "#", "published": True, "dish_count": 4},
                "2026-11-11": {"menu": "Menu Cycle B", "url": "#", "published": False, "dish_count": 3},
            },
            "LUNCH": {
                "2026-11-10": {"menu": "Menu Cycle B", "url": "#", "published": True, "dish_count": 5},
            },
            "DINNER": {
                "2026-11-12": {"menu": "Menu Cycle C", "url": "#", "published": True, "dish_count": 4},
            },
        },
        "assign_url": "#",
    }

    band = [
        {"label": "2026-11-09", "predicted": 540, "lower": 505, "upper": 575},
        {"label": "2026-11-10", "predicted": 598, "lower": 560, "upper": 636},
        {"label": "2026-11-11", "predicted": 512, "lower": 478, "upper": 546},
        {"label": "2026-11-12", "predicted": 623, "lower": 585, "upper": 661},
        {"label": "2026-11-13", "predicted": 651, "lower": 612, "upper": 690},
    ]

    context = {
        "figures": [            {"label": "Waste cost", "value": "₹18,420", "note": "Across 214 dish records", "tone": "loss"},
            {"label": "Forecast error", "value": "11.4%", "note": "62 forecasts scored"},
            {"label": "Average turnout", "value": "546", "note": "72.8% of registered strength"},
            {"label": "Portions to cook", "value": "1,284", "note": "Across today's plans"},
        ],
        "text_figures": [
            {"label": "Biggest cause", "value": "Over-preparation", "note": "A phrase steps down a size", "tone": "loss", "kind": "text"},
            {"label": "Biggest hall", "value": "North Block Mess", "note": "The words stay whole", "kind": "text"},
            {"label": "Prep mode", "value": "Against the forecast", "note": "Not a number", "kind": "text"},
            {"label": "Still open", "value": "Three codes", "note": "A figure that reads as words", "kind": "text"},
        ],
        "board": board,
        "band": band,
        "dishes": dishes,
        "field_errors": ["That code was not recognised"],
        "halls": DiningHall.objects.filter(is_active=True).order_by("name"),
        "meal_choices": MealType.choices,
        "tabs": [
            {"label": "Overview", "url": "#", "current": True},
            {"label": "Forecast", "url": "#", "count": 126},
            {"label": "Attendance", "url": "#"},
            {"label": "Menus", "url": "#", "count": 3},
        ],
        "specs": [
            {"name": "Portions to prepare", "value": "640"},
            {"name": "Safety margin", "value": "+8.0%", "note": "The margin this hall allows"},
            {"name": "Estimated cost", "value": "₹9,840"},
            {"name": "Leftover last time", "value": "38 portions", "tone": "loss"},
        ],
        "table_columns": [
            {"label": "Dish", "key": "dish"},
            {"label": "Category", "key": "category"},
            {"label": "Cost per portion", "key": "cost", "align": "right"},
        ],
        "table_rows": [
            {
                "dish": d.name,
                "category": d.get_category_display(),
                "cost": f"₹{costs.get(d.pk, {}).get('portion_cost_with_trim', 0):.2f}",
            }
            for d in dishes
        ],
    }
    return render(request, "design_system/index.html", context)
