"""Menu management: cycles, their items, and the schedule that publishes them.

The rules here are the ones a mess manager actually argues about, so they
live in one place rather than in the view:

* A menu cycle is a set of dishes per meal. Editing a cycle changes what
  the kitchen is told to cook the next time that cycle runs.
* A schedule row binds a cycle to a hall, a date and a meal. Publishing a
  row makes it visible to the kitchen and to the students.
* A cycle cannot be deleted while a published schedule still points at it.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import Count, Q, Sum

from apps.catalog.models import Dish
from apps.core.console import week_start
from apps.core.constants import MEAL_SERVICE_ORDER, MealType
from apps.menu.models import Menu, MenuItem, MenuSchedule


def menu_cycles() -> list[Menu]:
    """Every active cycle, with its item counts annotated."""
    return list(
        Menu.objects.filter(is_active=True)
        .annotate(item_count=Count("items", distinct=True))
        .order_by("name")
    )


def cycle_items(menu: Menu) -> dict[str, list[MenuItem]]:
    """The dishes in a cycle, grouped by meal and ordered by sequence."""
    grouped: dict[str, list[MenuItem]] = {m.value: [] for m in MealType}
    items = (
        menu.items.select_related("dish")
        .order_by("meal", "sequence", "dish__name")
    )
    for item in items:
        grouped.setdefault(item.meal, []).append(item)
    return grouped


def schedule_board(
    start: dt.date, hall=None, days: int = 7
) -> dict:
    """The schedule as a board: days across, meals down.

    Returns a structure the ``schedule_board`` component renders directly,
    so the template never has to do the grouping itself.
    """
    end = start + dt.timedelta(days=days - 1)
    rows = (
        MenuSchedule.objects.filter(date__gte=start, date__lte=end)
        .select_related("menu")
        .order_by("date", "meal")
    )
    if hall is not None:
        rows = rows.filter(hall=hall)

    cells: dict[str, dict[str, dict]] = {}
    for row in rows:
        day_key = row.date.isoformat()
        meal_key = row.meal
        cells.setdefault(meal_key, {})[day_key] = {
            # The cell is narrow, so it carries the short name and keeps the
            # full one for anyone who hovers or reads it aloud.
            "menu": row.menu.cycle_label or row.menu.code,
            "full_name": row.menu.name,
            "menu_code": row.menu.code,
            "published": row.is_published,
            "dish_count": row.menu.items.filter(meal=row.meal).count(),
            "id": row.id,
        }

    day_list = []
    for i in range(days):
        day = start + dt.timedelta(days=i)
        day_list.append(
            {
                "iso": day.isoformat(),
                "label": f"{day.day} {day.strftime('%b')}",
                "weekday": day.strftime("%a"),
                "date": day,
            }
        )

    # Only the meals the kitchen actually serves. A row of empty cells for
    # a snack service nobody runs is noise on the board. A mess that does run
    # snacks has a schedule row for them, and then the row belongs there.
    served = [m for m in MealType if m.value != MealType.SNACK.value]
    snack_rows = MenuSchedule.objects.filter(meal=MealType.SNACK.value)
    if hall is not None:
        snack_rows = snack_rows.filter(hall=hall)
    if snack_rows.exists():
        served.append(MealType.SNACK)

    return {
        "days": day_list,
        "meals": [
            {"code": m.value, "label": m.label}
            for m in sorted(served, key=lambda x: MEAL_SERVICE_ORDER.get(x.value, 9))
        ],
        "cells": cells,
        "start": start,
        "end": end,
    }


def publish_schedule(schedule_id: int, published: bool) -> MenuSchedule:
    """Publish or unpublish one schedule row."""
    row = MenuSchedule.objects.select_related("menu").get(pk=schedule_id)
    row.is_published = published
    if published and row.published_at is None:
        row.published_at = dt.datetime.now(dt.timezone.utc)
    row.save(update_fields=["is_published", "published_at", "updated_at"])
    return row


def cycle_summary(menu: Menu) -> dict:
    """What one cycle contains, for the cycle list and its detail panel."""
    items = menu.items.select_related("dish")
    by_meal: dict[str, dict] = {}
    for meal in MealType:
        meal_items = list(items.filter(meal=meal.value))
        by_meal[meal.value] = {
            "label": meal.label,
            "dishes": [i.dish.name for i in meal_items],
            "count": len(meal_items),
        }
    return {
        "menu": menu,
        "by_meal": by_meal,
        "total_dishes": items.count(),
        "scheduled": MenuSchedule.objects.filter(menu=menu).count(),
        "published": MenuSchedule.objects.filter(menu=menu, is_published=True).count(),
    }


def unassigned_dishes() -> list[Dish]:
    """Dishes that do not appear in any cycle, so they can be added."""
    used = MenuItem.objects.values_list("dish_id", flat=True)
    return list(Dish.objects.filter(is_active=True).exclude(pk__in=used).order_by("name"))


def create_cycle(name: str, code: str, cycle_label: str = "", description: str = "") -> Menu:
    """Create an empty cycle."""
    return Menu.objects.create(
        name=name,
        code=code.upper(),
        cycle_label=cycle_label,
        description=description,
    )


def set_cycle_items(menu: Menu, meal: str, dish_ids: list[int]) -> int:
    """Replace the dishes for one meal of a cycle.

    Returns the number of items written. The sequence is the order the
    dishes were given in, because that is the order they are served in.
    """
    menu.items.filter(meal=meal).delete()
    written = 0
    for sequence, dish_id in enumerate(dish_ids):
        MenuItem.objects.create(menu=menu, meal=meal, dish_id=dish_id, sequence=sequence)
        written += 1
    return written


def cycle_share_totals(menu: Menu) -> dict[str, Decimal]:
    """The expected share of portions per dish, for the planning preview."""
    totals: dict[str, Decimal] = {}
    for item in menu.items.select_related("dish"):
        key = item.dish.name
        totals[key] = totals.get(key, Decimal("0")) + (item.expected_share or Decimal("0"))
    return totals


# ---------------------------------------------------------------------------
# Daily and weekly menus
# ---------------------------------------------------------------------------
# The board is edited one cell at a time, which is right for fixing a day and
# wrong for planning a week. A mess manager plans the week: this hall runs
# this cycle on these days, that hall runs that one. So there are two bulk
# operations, and both go through the same writer as the single cell.


def assign_slot(hall, on_date: dt.date, meal: str, menu: Menu, published: bool = False):
    """Point one hall-meal-date at a cycle, creating the row if it is new.

    The slot is unique on (hall, date, meal), so the row is found by those
    three fields and the cycle on it is changed. A row that already exists
    keeps its published state, because a schedule that the kitchen has
    already been told about should not quietly become unpublished because
    somebody edited it.
    """
    row, created = MenuSchedule.objects.get_or_create(
        hall=hall,
        date=on_date,
        meal=meal,
        defaults={"menu": menu, "is_published": published},
    )
    if not created and row.menu_id != menu.pk:
        row.menu = menu
        row.save(update_fields=["menu", "updated_at"])
    return row


def assign_day(
    hall,
    on_date: dt.date,
    menu: Menu,
    meals: list[str] | None = None,
    published: bool = False,
) -> int:
    """A daily menu: one cycle for every meal of one hall on one date.

    Returns the number of slots written.
    """
    wanted = meals or [m.value for m in MealType]
    written = 0
    for meal in wanted:
        assign_slot(hall, on_date, meal, menu, published=published)
        written += 1
    return written


def assign_week(
    hall,
    start: dt.date,
    menus: list[Menu],
    meals: list[str] | None = None,
    days: int = 7,
    published: bool = False,
) -> int:
    """A weekly menu: a rotation of cycles across the days of one week.

    ``menus`` is the rotation. One cycle means that cycle every day. Three
    cycles means Monday takes the first, Tuesday the second, Wednesday the
    first again, and so on - which is how a mess actually rotates its
    dishes.

    Returns the number of slots written.
    """
    if not menus:
        raise ValueError("A weekly menu needs at least one cycle.")

    wanted = meals or [m.value for m in MealType]
    written = 0
    for offset in range(days):
        on_date = start + dt.timedelta(days=offset)
        menu = menus[offset % len(menus)]
        for meal in wanted:
            assign_slot(hall, on_date, meal, menu, published=published)
            written += 1
    return written


def rotation_preview(menus: list[Menu], days: int = 7) -> list[dict]:
    """What a rotation would produce, so the manager sees it before writing."""
    if not menus:
        return []
    preview = []
    for offset in range(days):
        on_date = week_start(dt.date.today()) + dt.timedelta(days=offset)
        preview.append(
            {
                "date": on_date,
                "weekday": on_date.strftime("%a"),
                "label": f"{on_date.day} {on_date.strftime('%b')}",
                "menu": menus[offset % len(menus)],
            }
        )
    return preview
