"""M8 - Waste measurement and costing.

Waste is measured per dish per service, in two units:

* **quantity** - kilograms of food left over (portions x portion size), which
  is what the kitchen can relate to the bin.
* **cost** - rupees, derived from the dish's recipe and the current cost of
  every ingredient in it.

The cost figure is the one the sales argument rests on, so it is computed from
the same recipe and the same cost rates that produced the preparation plan.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models

from apps.core.constants import WasteCause
from apps.core.models import TimeStampedModel


class WasteRecord(TimeStampedModel):
    """What was wasted at one dish of one service, and what it cost."""

    service_actual = models.ForeignKey(
        "actuals.ServiceActual", on_delete=models.CASCADE, related_name="waste_records"
    )
    dish = models.ForeignKey("catalog.Dish", on_delete=models.PROTECT, related_name="waste_records")
    service = models.ForeignKey(
        "attendance.MealService", on_delete=models.CASCADE, related_name="waste_records"
    )
    #: Denormalised copy of the service date so waste can be indexed and
    #: aggregated by period without joining through the service on every query.
    service_date = models.DateField(db_index=True)
    hall = models.ForeignKey(
        "catalog.DiningHall", on_delete=models.CASCADE, null=True, blank=True, related_name="waste_records"
    )
    meal = models.CharField(max_length=16, blank=True, default="")

    leftover_portions = models.PositiveIntegerField(default=0)
    #: Weight of the leftover food.
    waste_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    unit = models.CharField(max_length=8, default="kg")
    #: Cost of one portion of this dish, from the active recipe.
    cost_per_portion = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    waste_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    #: What the forecast expected for this dish - the benchmark for over-preparation.
    forecast_portions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    over_prepared_portions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    cause = models.CharField(
        max_length=24, choices=WasteCause.choices, default=WasteCause.OVER_PREPARATION, db_index=True
    )
    computed_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-service_date"]
        constraints = [
            models.UniqueConstraint(fields=["service_actual", "dish"], name="uniq_waste_dish"),
        ]
        indexes = [
            models.Index(fields=["hall", "service_date"], name="idx_waste_hall_date"),
            models.Index(fields=["dish", "-service_date"], name="idx_waste_dish_date"),
        ]

    def __str__(self) -> str:
        return f"Waste {self.dish.name} @ {self.service}: {self.leftover_portions} portions, Rs {self.waste_cost}"
