"""Registration codes.

A registration code is issued by the mess office to the person who will
use the account. It carries the role the account is created with, so the
role a new user gets is decided by whoever issued the code rather than by
the person registering.

A code is single use. Once it is redeemed it is spent, and it records who
redeemed it and when.
"""

from __future__ import annotations

import datetime as dt
import secrets

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


def _new_code() -> str:
    """A code that is short enough to read over the phone and long enough to be safe."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def default_expiry() -> dt.date:
    """A code is good for a fortnight."""
    return dt.date.today() + dt.timedelta(days=14)


class RegistrationCode(TimeStampedModel):
    """One invitation to register, carrying the role it grants."""

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        REDEEMED = "REDEEMED", "Redeemed"
        REVOKED = "REVOKED", "Revoked"

    code = models.CharField(max_length=16, unique=True, default=_new_code, editable=False)
    role = models.CharField(max_length=32, choices=[], default="")
    hall = models.ForeignKey(
        "catalog.DiningHall",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registration_codes",
        help_text="The hall this code assigns, for kitchen staff and students.",
    )
    full_name = models.CharField(max_length=160, blank=True, default="")
    student_identifier = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True)
    expires_on = models.DateField(default=default_expiry)
    redeemed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registration_codes_redeemed",
    )
    redeemed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.code} ({self.get_status_display()})"

    @property
    def is_usable(self) -> bool:
        """True when the code can still be redeemed."""
        return self.status == self.Status.OPEN and self.expires_on >= dt.date.today()

    def redeem(self, user) -> None:
        """Spend the code against a user."""
        self.status = self.Status.REDEEMED
        self.redeemed_by = user
        self.redeemed_at = timezone.now()
        self.save(update_fields=["status", "redeemed_by", "redeemed_at", "updated_at"])

    @classmethod
    def issue(cls, role: str, **kwargs) -> "RegistrationCode":
        """Issue a code granting ``role``."""
        from apps.accounts.models import User

        valid = {choice[0] for choice in User.Role.choices}
        if role not in valid:
            raise ValueError(f"{role} is not a role")
        return cls.objects.create(role=role, **kwargs)
