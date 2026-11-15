"""User accounts and the six roles named in the specification."""

from __future__ import annotations

import datetime as dt
import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """Platform user.

    The specification names six roles. They are modelled as a single ``role``
    field rather than Django permission groups because the role set is fixed and
    small, and every screen needs a simple "can this person do X" answer.
    """

    class Role(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        KITCHEN_STAFF = "KITCHEN_STAFF", "Kitchen Staff"
        MESS_MANAGER = "MESS_MANAGER", "Mess Manager"
        MESS_ADMIN = "MESS_ADMIN", "Mess Administrator"
        FINANCE_OFFICER = "FINANCE_OFFICER", "Finance Officer"
        ADMINISTRATOR = "ADMINISTRATOR", "Administrator"

    role = models.CharField(max_length=32, choices=Role.choices, default=Role.STUDENT, db_index=True)
    #: Credential encoded in the student QR code / tapped by the RFID reader.
    student_identifier = models.CharField(max_length=64, unique=True, null=True, blank=True)
    #: Hall a kitchen staff member is assigned to (scopes their permissions).
    hall = models.ForeignKey(
        "catalog.DiningHall",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff",
    )

    class Meta:
        ordering = ["username"]

    def __str__(self) -> str:
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_staff_role(self) -> bool:
        return self.role in {self.Role.KITCHEN_STAFF, self.Role.ADMINISTRATOR}

    @property
    def is_management_role(self) -> bool:
        """True for the roles that manage the platform rather than use it."""
        return self.role in {
            self.Role.MESS_MANAGER,
            self.Role.MESS_ADMIN,
            self.Role.ADMINISTRATOR,
        }


class PasswordResetToken(models.Model):
    """A single-use, time-limited password reset token.

    Tokens are unpredictable, expire after ``PASSWORD_RESET_TIMEOUT`` seconds,
    and are invalidated the moment they are used, so a captured link cannot be
    replayed. Whether an email is registered is never confirmed or denied by
    the reset flow.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="password_reset_tokens"
    )
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"reset for {self.user.username}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.created_at + dt.timedelta(
            seconds=settings.PASSWORD_RESET_TIMEOUT
        )

    @classmethod
    def create_for_user(cls, user) -> "PasswordResetToken":
        return cls.objects.create(
            user=user,
            token=secrets.token_urlsafe(32),
        )
