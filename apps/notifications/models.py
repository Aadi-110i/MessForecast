"""Notifications and communication (specification section 11).

Notifications are written to an outbox first and dispatched afterwards. That
way a failed SMS gateway cannot lose the record that the kitchen was told to
prepare 540 portions, and the outbox doubles as an audit trail.
"""

from __future__ import annotations

from django.db import models

from apps.core.constants import NotificationChannel, NotificationKind
from apps.core.models import TimeStampedModel


class Notification(TimeStampedModel):
    """One outbound message about one service or one event."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"
        SUPPRESSED = "SUPPRESSED", "Suppressed"

    kind = models.CharField(max_length=32, choices=NotificationKind.choices, db_index=True)
    channel = models.CharField(
        max_length=16, choices=NotificationChannel.choices, default=NotificationChannel.IN_APP
    )
    recipient = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications"
    )
    role_target = models.CharField(max_length=32, blank=True, default="")
    hall = models.ForeignKey(
        "catalog.DiningHall", on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
    )
    service = models.ForeignKey(
        "attendance.MealService", on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
    )
    subject = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} -> {self.subject}"
