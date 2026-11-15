"""M7 - Post-service actuals.

After a service the kitchen records what it prepared, what it served and what
was left over. These three numbers are the raw material for waste costing and
for measuring how good the forecast was.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models

from apps.core.constants import PrepMode
from apps.core.models import TimeStampedModel


class ServiceActual(TimeStampedModel):
    """What actually happened at one service."""

    service = models.OneToOneField(
        "attendance.MealService", on_delete=models.CASCADE, related_name="actual"
    )
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="recorded_actuals"
    )
    recorded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    prepared_portions_total = models.PositiveIntegerField(default=0)
    served_portions_total = models.PositiveIntegerField(default=0)
    leftover_portions_total = models.PositiveIntegerField(default=0)

    #: How the food for this service was actually prepared. This is the field
    #: the before/after saving comparison turns on: the baseline period used
    #: the registered strength, the live period uses the forecast.
    prep_mode = models.CharField(
        max_length=32, choices=PrepMode.choices, default=PrepMode.FORECAST_GUIDED, db_index=True
    )
    #: Attendance as counted by the kitchen's own tally, when it differs from
    #: the scan count (useful when a hall runs on manual entry only).
    attendance_actual = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-recorded_at"]
        verbose_name_plural = "Service actuals"

    def __str__(self) -> str:
        return f"Actual {self.service}: prepared {self.prepared_portions_total}, leftover {self.leftover_portions_total}"

    @property
    def waste_portions(self) -> int:
        return max(0, self.prepared_portions_total - self.served_portions_total)


class DishActual(TimeStampedModel):
    """Per-dish breakdown of what was prepared, served and left over."""

    service_actual = models.ForeignKey(ServiceActual, on_delete=models.CASCADE, related_name="dish_actuals")
    dish = models.ForeignKey("catalog.Dish", on_delete=models.PROTECT, related_name="dish_actuals")
    prepared_portions = models.PositiveIntegerField(default=0)
    served_portions = models.PositiveIntegerField(default=0)
    leftover_portions = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["service_actual", "dish"]
        constraints = [
            models.UniqueConstraint(fields=["service_actual", "dish"], name="uniq_dish_actual"),
        ]

    def __str__(self) -> str:
        return f"{self.dish.name}: prepared {self.prepared_portions}, served {self.served_portions}, leftover {self.leftover_portions}"

    def save(self, *args, **kwargs):
        if not self.leftover_portions:
            self.leftover_portions = max(0, self.prepared_portions - self.served_portions)
        return super().save(*args, **kwargs)

    @property
    def waste_portions(self) -> int:
        return max(0, self.prepared_portions - self.served_portions)
