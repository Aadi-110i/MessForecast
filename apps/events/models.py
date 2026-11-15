"""M3 - Calendar & event registry, plus the service-level configuration.

The event registry is what makes the forecaster more than a moving average: an
exam period, a festival or a vacation moves demand in a way the weekday
pattern alone cannot explain.

The service-level configuration answers a different question - "how much
over-preparation is this hall willing to tolerate?" - and drives the safety
margin applied when a forecast is turned into a preparation quantity.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import models

from apps.core.constants import EventType, MealType
from apps.core.models import TimeStampedModel

#: How many portions of food a student typically takes in one meal. A student
#: at lunch takes rice, a dal, a curry and sometimes salad — so the kitchen
#: cooks more portions than there are students. Every conversion between
#: "students" and "portions" goes through this number.
DEFAULT_PORTIONS_PER_STUDENT = {
    MealType.BREAKFAST: Decimal("1.60"),
    MealType.LUNCH: Decimal("2.60"),
    MealType.DINNER: Decimal("2.30"),
    MealType.SNACK: Decimal("1.20"),
}


def default_portions_per_student(meal: str) -> Decimal:
    return DEFAULT_PORTIONS_PER_STUDENT.get(meal, Decimal("2.40"))


class CalendarEvent(TimeStampedModel):
    """A dated event that changes expected demand.

    ``impact_factor`` is a multiplier on the base demand level: 1.20 means
    "twenty per cent more people than a normal day", 0.30 means "almost nobody
    comes". Overlapping events multiply.
    """

    name = models.CharField(max_length=160)
    event_type = models.CharField(max_length=16, choices=EventType.choices, default=EventType.OTHER, db_index=True)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    impact_factor = models.DecimalField(
        max_digits=6, decimal_places=3, default=Decimal("1.000"),
        help_text="Multiplier on expected demand. 1.000 = no effect.",
    )
    affects_meals = models.CharField(
        max_length=64, blank=True, default="",
        help_text="Comma separated meal codes this event touches. Empty means every meal.",
    )
    affects_halls = models.ManyToManyField(
        "catalog.DiningHall", blank=True, related_name="events",
        help_text="Empty means every hall.",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-start_date", "name"]
        indexes = [models.Index(fields=["start_date", "end_date"], name="idx_event_window")]

    def __str__(self) -> str:
        return f"{self.name} ({self.start_date} to {self.end_date})"

    def covers(self, on_date: dt.date) -> bool:
        return self.start_date <= on_date <= self.end_date

    def applies_to_meal(self, meal: str) -> bool:
        if not self.affects_meals:
            return True
        return meal in [m.strip().upper() for m in self.affects_meals.split(",")]

    def applies_to_hall(self, hall) -> bool:
        # Uses the prefetched relation when it is available, so the calendar
        # can be walked many times without a query per event per date.
        hall_ids = {hall.pk for hall in self.affects_halls.all()}
        if not hall_ids:
            return True
        return hall.pk in hall_ids

    def factor_for(self, on_date: dt.date, meal: str, hall) -> Decimal:
        """The multiplier this event contributes on ``on_date``."""
        if not self.is_active or not self.covers(on_date):
            return Decimal("1")
        if not self.applies_to_meal(meal) or not self.applies_to_hall(hall):
            return Decimal("1")
        return self.impact_factor


class ServiceLevelConfig(TimeStampedModel):
    """How much over-preparation a hall will accept for a meal.

    The most specific row wins: (hall, meal) beats (hall, any meal) beats
    (any hall, meal) beats the global default.
    """

    hall = models.ForeignKey(
        "catalog.DiningHall", on_delete=models.CASCADE, null=True, blank=True, related_name="service_levels"
    )
    meal = models.CharField(max_length=16, choices=MealType.choices, null=True, blank=True)
    acceptable_overprep_pct = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("8.00"),
        help_text="Percentage of extra portions the kitchen accepts preparing to avoid running out.",
    )
    max_overprep_pct = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("18.00"),
        help_text="Hard ceiling. The preparation plan will not exceed this.",
    )
    min_buffer_portions = models.PositiveIntegerField(
        default=10, help_text="Absolute floor of extra portions regardless of percentage."
    )
    portions_per_student = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("2.40"),
        help_text=(
            "How many portions of food one student takes in this meal. "
            "Used to convert attendance into portions to prepare."
        ),
    )
    effective_from = models.DateField(default=dt.date.today)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-effective_from", "hall", "meal"]

    def __str__(self) -> str:
        hall = self.hall.code if self.hall else "all halls"
        meal = self.meal or "all meals"
        return f"{hall} / {meal}: +{self.acceptable_overprep_pct}%"

    @classmethod
    def resolve(cls, hall, meal: str, on_date: dt.date | None = None) -> "ServiceLevelConfig":
        """Return the configuration that applies to (hall, meal) on ``on_date``."""
        on_date = on_date or dt.date.today()
        candidates = cls.objects.filter(effective_from__lte=on_date).filter(
            models.Q(hall=hall) | models.Q(hall__isnull=True)
        )
        exact_hall_meal = candidates.filter(hall=hall, meal=meal).order_by("-effective_from").first()
        if exact_hall_meal:
            return exact_hall_meal
        exact_hall_any = candidates.filter(hall=hall, meal__isnull=True).order_by("-effective_from").first()
        if exact_hall_any:
            return exact_hall_any
        any_hall_meal = candidates.filter(hall__isnull=True, meal=meal).order_by("-effective_from").first()
        if any_hall_meal:
            return any_hall_meal
        global_default = cls.objects.filter(hall__isnull=True, meal__isnull=True).order_by(
            "-effective_from"
        ).first()
        if global_default:
            return global_default
        # Unsaved fallback carrying the per-meal default.
        fallback = cls(effective_from=on_date)
        fallback.portions_per_student = default_portions_per_student(meal)
        return fallback
