"""Abstract base models shared by every domain app."""

from django.db import models


class TimeStampedModel(models.Model):
    """Adds ``created_at`` / ``updated_at`` to every concrete model."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """Adds a client-visible UUID primary-key style identifier.

    Offline clients generate their own UUIDs for records that must be idempotent
    on sync. Exposing it as a normal field (rather than the primary key) keeps
    integer primary keys while giving the client a stable dedup key.
    """

    uuid = models.UUIDField(default=None, null=True, blank=True, editable=False)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.uuid is None:
            import uuid as _uuid

            self.uuid = _uuid.uuid4()
        return super().save(*args, **kwargs)
