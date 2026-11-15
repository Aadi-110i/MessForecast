"""M6 - Preparation plans and the ingredient indent.

A *preparation plan* answers "how many portions of each dish should we cook?".
An *ingredient indent* answers "how much of each raw material must we buy?".
The chain is: forecast -> portions -> dishes -> recipe -> ingredients -> money.
"""

from __future__ import annotations

from decimal import Decimal

import django.utils.timezone
from django.db import models

from apps.core.models import TimeStampedModel


class PreparationPlan(TimeStampedModel):
    """What the kitchen should prepare for one service."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published to kitchen"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged by kitchen"

    service = models.OneToOneField(
        "attendance.MealService", on_delete=models.CASCADE, related_name="preparation_plan"
    )
    forecast = models.ForeignKey(
        "forecasting.Forecast", on_delete=models.SET_NULL, null=True, blank=True, related_name="preparation_plans"
    )
    generated_at = models.DateTimeField(default=django.utils.timezone.now)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)

    #: The forecast the plan was built from.
    attendance_target = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    #: Students converted into portions using the service-level ratio.
    portions_target = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    #: Over-preparation allowance applied, from the service-level configuration.
    safety_margin_pct = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))
    #: Total portions to prepare across all dishes on the menu.
    portions_to_prepare = models.PositiveIntegerField(default=0)
    #: What that means as a percentage over the forecast.
    over_preparation_pct = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))
    estimated_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    #: Plain-language brief shown on the kitchen screen.
    guidance_text = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self) -> str:
        return f"Plan {self.service}: {self.portions_to_prepare} portions"

    @property
    def dish_count(self) -> int:
        return self.lines.count()


class PreparationLine(TimeStampedModel):
    """One dish on the menu and the number of portions to cook."""

    plan = models.ForeignKey(PreparationPlan, on_delete=models.CASCADE, related_name="lines")
    dish = models.ForeignKey("catalog.Dish", on_delete=models.PROTECT, related_name="preparation_lines")
    portions = models.PositiveIntegerField(default=0)
    #: Share of the forecast that this dish is expected to take.
    expected_share = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0"))
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    notes = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        ordering = ["plan", "-portions"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "dish"], name="uniq_plan_dish"),
        ]

    def __str__(self) -> str:
        return f"{self.dish.name} x{self.portions}"


class IngredientIndent(TimeStampedModel):
    """The procurement list derived from a preparation plan."""

    plan = models.OneToOneField(
        PreparationPlan, on_delete=models.CASCADE, related_name="indent"
    )
    hall = models.ForeignKey("catalog.DiningHall", on_delete=models.CASCADE, related_name="indents")
    date = models.DateField(db_index=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    total_estimated_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    line_count = models.PositiveIntegerField(default=0)
    #: The indent rendered in the procurement format the kitchen already uses.
    procurement_text = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-generated_at"]
        verbose_name_plural = "Ingredient indents"

    def __str__(self) -> str:
        return f"Indent {self.hall.code} {self.date}"


class IndentLine(TimeStampedModel):
    """One raw material on the indent."""

    indent = models.ForeignKey(IngredientIndent, on_delete=models.CASCADE, related_name="lines")
    ingredient = models.ForeignKey("catalog.Ingredient", on_delete=models.PROTECT, related_name="indent_lines")
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    unit = models.CharField(max_length=12, blank=True, default="kg")
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0"))
    estimated_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    #: Dishes that contributed to this line.
    source_dishes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["indent", "ingredient__name"]
        constraints = [
            models.UniqueConstraint(fields=["indent", "ingredient"], name="uniq_indent_ingredient"),
        ]

    def __str__(self) -> str:
        return f"{self.ingredient.name} {self.quantity} {self.unit}"

    @property
    def packs(self) -> Decimal:
        """How many purchase packs this line needs."""
        pack_size = self.ingredient.purchase_pack_size or Decimal("1")
        if pack_size <= 0:
            return Decimal("0")
        from apps.core.utils import q2

        return q2(self.quantity / pack_size)
