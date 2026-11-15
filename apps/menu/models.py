"""M1 (continued) - Menu cycles, the dishes they contain and the calendar that
assigns a menu to a hall and a meal on a given day."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import models

from apps.core.constants import MealType
from apps.core.models import TimeStampedModel


class Menu(TimeStampedModel):
    """A named set of dishes offered for one or more meals (a 'menu cycle')."""

    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=24, unique=True)
    cycle_label = models.CharField(max_length=64, blank=True, default="")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def items_for_meal(self, meal: str):
        return self.items.filter(meal=meal).select_related("dish").order_by("sequence")


class MenuItem(TimeStampedModel):
    """One dish inside a menu, for one meal."""

    menu = models.ForeignKey(Menu, on_delete=models.CASCADE, related_name="items")
    meal = models.CharField(max_length=16, choices=MealType.choices, db_index=True)
    dish = models.ForeignKey("catalog.Dish", on_delete=models.PROTECT, related_name="menu_items")
    sequence = models.PositiveIntegerField(default=0)
    expected_share = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal("0"),
        help_text=(
            "Share of the forecast attendance expected to take this dish. "
            "Zero means 'not yet learned'; the analysis module fills it in from history."
        ),
    )

    class Meta:
        ordering = ["menu", "meal", "sequence"]
        constraints = [
            models.UniqueConstraint(fields=["menu", "meal", "dish"], name="uniq_menu_meal_dish"),
        ]

    def __str__(self) -> str:
        return f"{self.menu.name} / {self.get_meal_display()} / {self.dish.name}"


class MenuSchedule(TimeStampedModel):
    """Assignment of a menu to a hall + meal on a date.

    One row per (hall, date, meal). The menu-schedule calendar is the input to
    the forecasting engine: the kitchen cannot plan a menu for a meal that has
    no schedule row, and a schedule row is what makes a service exist.
    """

    menu = models.ForeignKey(Menu, on_delete=models.PROTECT, related_name="schedules")
    hall = models.ForeignKey("catalog.DiningHall", on_delete=models.CASCADE, related_name="schedules")
    date = models.DateField(db_index=True)
    meal = models.CharField(max_length=16, choices=MealType.choices, db_index=True)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["date", "meal", "hall"]
        constraints = [
            models.UniqueConstraint(fields=["hall", "date", "meal"], name="uniq_schedule_slot"),
        ]

    def __str__(self) -> str:
        return f"{self.hall.code} {self.date} {self.get_meal_display()} -> {self.menu.code}"
