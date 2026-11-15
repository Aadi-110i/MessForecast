"""M2 - Meal services and the attendance captured against them.

The specification requires attendance capture to work offline. Every offline
record carries a client-generated UUID; the server stores it under a unique
constraint and silently ignores a UUID it already holds. That is the whole
sync-idempotency story on the PostgreSQL track: a duplicate insert simply
fails the constraint and is discarded.
"""

from __future__ import annotations

import datetime as dt
import uuid as uuid_lib
from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.constants import CaptureMethod, MealType, PrepMode
from apps.core.models import TimeStampedModel


class MealService(TimeStampedModel):
    """One meal served at one hall on one date."""

    hall = models.ForeignKey("catalog.DiningHall", on_delete=models.CASCADE, related_name="meal_services")
    date = models.DateField(db_index=True)
    meal = models.CharField(max_length=16, choices=MealType.choices, db_index=True)
    registered_strength = models.PositiveIntegerField(
        default=0,
        help_text="Students registered with the ERP for this mess. This is what the kitchen used to cook against.",
    )
    prep_mode = models.CharField(
        max_length=32, choices=PrepMode.choices, default=PrepMode.REGISTERED_STRENGTH, db_index=True
    )
    opens_at = models.TimeField(null=True, blank=True)
    closes_at = models.TimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    #: Denormalised counter kept in step with the AttendanceRecord rows.
    #: The records remain the source of truth; this exists so the forecasting
    #: engine can read a service's demand without a COUNT(*) per service.
    attendance_count = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["-date", "meal", "hall"]
        constraints = [
            models.UniqueConstraint(fields=["hall", "date", "meal"], name="uniq_meal_service_slot"),
        ]
        indexes = [
            models.Index(fields=["hall", "meal", "date"], name="idx_service_hall_meal_date"),
            models.Index(fields=["date", "meal"], name="idx_service_date_meal"),
        ]

    def __str__(self) -> str:
        return f"{self.hall.code} {self.date} {self.get_meal_display()}"

    @property
    def attendance_rate(self) -> Decimal:
        """Attendance as a share of registered strength (0-100)."""
        if not self.registered_strength:
            return Decimal("0")
        return Decimal(self.attendance_count) / Decimal(self.registered_strength) * 100


class AttendanceRecord(TimeStampedModel):
    """A single attendance capture.

    ``client_uuid`` is the idempotency key. The tablet generates it before the
    scan is queued offline, so a retried sync cannot create a second record.
    """

    client_uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    service = models.ForeignKey(MealService, on_delete=models.CASCADE, related_name="attendance_records")
    student = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="attendance_records"
    )
    student_identifier = models.CharField(max_length=64, db_index=True)
    method = models.CharField(max_length=16, choices=CaptureMethod.choices, default=CaptureMethod.QR)
    captured_at = models.DateTimeField(default=timezone.now)
    device_id = models.CharField(max_length=64, blank=True, default="")
    captured_offline = models.BooleanField(default=False)
    synced_at = models.DateTimeField(null=True, blank=True)
    hall = models.ForeignKey(
        "catalog.DiningHall", on_delete=models.CASCADE, null=True, blank=True, related_name="attendance_records"
    )
    meal = models.CharField(max_length=16, choices=MealType.choices, blank=True, default="")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-captured_at"]
        indexes = [
            models.Index(fields=["service", "method"], name="idx_att_service_method"),
            models.Index(fields=["service", "student_identifier"], name="idx_att_service_student"),
        ]

    def __str__(self) -> str:
        return f"{self.student_identifier} @ {self.service_id}"

    def save(self, *args, **kwargs):
        if self.hall_id is None and self.service_id:
            self.hall_id = self.service.hall_id
            self.meal = self.service.meal
        if self.synced_at is None:
            self.synced_at = timezone.now()
        return super().save(*args, **kwargs)


class AttendanceAudit(TimeStampedModel):
    """Record of a sync batch: what arrived, what was a duplicate, what failed.

    The duplicate counter is the evidence for the acceptance criterion
    "attendance capture works offline and syncs without duplication".
    """

    device_id = models.CharField(max_length=64, db_index=True)
    received = models.PositiveIntegerField(default=0)
    created = models.PositiveIntegerField(default=0)
    duplicates = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    detail = models.JSONField(default=dict, blank=True)
    batch_started_at = models.DateTimeField(default=timezone.now)
    batch_finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-batch_started_at"]
        verbose_name_plural = "Attendance audits"

    def __str__(self) -> str:
        return f"sync {self.device_id}: {self.created} new / {self.duplicates} duplicate"
