"""Test helpers — small explicit builders rather than a fixture library.

Every builder returns real objects in a real database, so the tests exercise
the same code paths the application uses.
"""

from __future__ import annotations

import datetime as dt
import uuid as uuid_lib
from decimal import Decimal

from apps.accounts.models import User
from apps.actuals.models import DishActual, ServiceActual
from apps.attendance.models import MealService
from apps.catalog.models import CostRate, DiningHall, Dish, Ingredient, Recipe, RecipeItem
from apps.menu.models import Menu, MenuItem, MenuSchedule


def make_hall(code="NORTH", name="North Block Mess", registered=100, capacity=200):
    return DiningHall.objects.create(
        code=code, name=name, capacity=capacity, registered_strength=registered
    )


def make_ingredient(code="RICE", name="Rice", unit="kg", cost="45"):
    ingredient = Ingredient.objects.create(
        code=code,
        name=name,
        base_unit=unit,
        purchase_pack_size=Decimal("25"),
        purchase_pack_unit=f"25 {unit}",
    )
    CostRate.objects.create(
        ingredient=ingredient,
        hall=None,
        unit_cost=Decimal(cost),
        effective_from=dt.date(2026, 1, 1),
        source="test",
    )
    return ingredient


def make_dish(code="RICE_DISH", name="Steamed Rice", serving="200"):
    return Dish.objects.create(
        code=code, name=name, category="STAPLE", serving_size_g=Decimal(serving)
    )


def make_recipe(dish, lines, version=1):
    """``lines`` is a list of ``(ingredient, quantity, trim_loss_pct)``."""
    recipe = Recipe.objects.create(
        dish=dish, version=version, effective_from=dt.date(2026, 1, 1)
    )
    for ingredient, quantity, trim in lines:
        RecipeItem.objects.create(
            recipe=recipe,
            ingredient=ingredient,
            quantity=Decimal(quantity),
            trim_loss_pct=Decimal(trim),
        )
    return recipe


def make_menu(code="MENU_A", name="Menu Cycle A"):
    return Menu.objects.create(code=code, name=name)


def add_dish_to_menu(menu, dish, meal="LUNCH", share="0.25", sequence=0):
    return MenuItem.objects.create(
        menu=menu, meal=meal, dish=dish, sequence=sequence, expected_share=Decimal(share)
    )


def schedule_menu(menu, hall, on_date, meal="LUNCH"):
    return MenuSchedule.objects.create(
        menu=menu, hall=hall, date=on_date, meal=meal, is_published=True
    )


def make_service(hall, on_date, meal="LUNCH", registered=100, attendance=None):
    service = MealService.objects.create(
        hall=hall,
        date=on_date,
        meal=meal,
        registered_strength=registered,
        attendance_count=attendance or 0,
    )
    return service


def make_actual(service, prepared=100, served=80, prep_mode="FORECAST_GUIDED", dishes=None):
    """``dishes`` is a list of ``(dish, prepared, served)``."""
    actual = ServiceActual.objects.create(
        service=service,
        prepared_portions_total=prepared,
        served_portions_total=served,
        leftover_portions_total=max(0, prepared - served),
        prep_mode=prep_mode,
    )
    for dish, dish_prepared, dish_served in dishes or []:
        DishActual.objects.create(
            service_actual=actual,
            dish=dish,
            prepared_portions=dish_prepared,
            served_portions=dish_served,
            leftover_portions=max(0, dish_prepared - dish_served),
        )
    return actual


def make_user(username="tester", role=User.Role.MESS_MANAGER, identifier=None):
    return User.objects.create_user(
        username=username,
        password="pass1234",
        role=role,
        student_identifier=identifier or f"{username}-ID",
    )


def scan_payload(service, identifier, client_uuid=None, method="QR", offline=True):
    return {
        "client_uuid": client_uuid or str(uuid_lib.uuid4()),
        "service_id": service.id,
        "hall_id": service.hall_id,
        "date": service.date.isoformat(),
        "meal": service.meal,
        "student_identifier": identifier,
        "method": method,
        "captured_at": dt.datetime.now().isoformat(),
        "device_id": "test-tablet",
        "captured_offline": offline,
    }
