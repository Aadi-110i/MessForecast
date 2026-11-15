"""M5 - Stored forecasts.

A forecast is attached to exactly one meal service. Keeping it as a row (not a
view) means the accuracy report can compare, weeks later, the number the
kitchen was given against the number that actually turned up.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel


class Forecast(TimeStampedModel):
    """A predicted attendance for one service, with a confidence range."""

    service = models.OneToOneField(
        "attendance.MealService", on_delete=models.CASCADE, related_name="forecast"
    )
    method = models.CharField(max_length=64)
    model_version = models.CharField(max_length=32)
    generated_at = models.DateTimeField(auto_now_add=True, db_index=True)
    horizon_days = models.PositiveIntegerField(default=7)

    predicted_attendance = models.DecimalField(max_digits=12, decimal_places=2)
    lower_bound = models.DecimalField(max_digits=12, decimal_places=2)
    upper_bound = models.DecimalField(max_digits=12, decimal_places=2)
    confidence_level = models.DecimalField(max_digits=5, decimal_places=3, default=Decimal("0.800"))

    # The workings, kept so the number can be explained rather than trusted blindly.
    base_level = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    weekday_factor = models.DecimalField(max_digits=9, decimal_places=4, default=Decimal("1"))
    event_factor = models.DecimalField(max_digits=9, decimal_places=4, default=Decimal("1"))
    trend_pct = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    rmse = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    mape = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))

    #: Hash of the inputs that produced this forecast. Two runs over the same
    #: history must produce the same signature and the same numbers.
    input_signature = models.CharField(max_length=64, db_index=True)
    explanation = models.TextField(blank=True, default="")
    is_fallback = models.BooleanField(default=False)
    observations_used = models.PositiveIntegerField(default=0)
    context = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-generated_at"]
        indexes = [
            models.Index(fields=["service", "-generated_at"], name="idx_forecast_service"),
        ]

    def __str__(self) -> str:
        return f"Forecast {self.service}: {self.predicted_attendance} ({self.lower_bound}-{self.upper_bound})"

    @property
    def interval_width(self) -> Decimal:
        return self.upper_bound - self.lower_bound

    def absolute_error(self) -> Decimal | None:
        """Signed error against the attendance that actually turned up."""
        actual = self.service.attendance_count
        if not actual:
            return None
        return Decimal(actual) - self.predicted_attendance

    def absolute_percentage_error(self) -> Decimal | None:
        """Absolute percentage error (the MAPE contribution of this forecast)."""
        actual = self.service.attendance_count
        if not actual:
            return None
        return abs(Decimal(actual) - self.predicted_attendance) / Decimal(actual) * Decimal("100")
