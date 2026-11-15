"""Celery tasks for notifications (Track P)."""

from __future__ import annotations

import datetime as dt

from celery import shared_task
from django.utils import timezone


@shared_task(name="notifications.tasks.dispatch_preparation_guidance")
def dispatch_preparation_guidance(today: str | None = None) -> dict:
    """Send tomorrow's preparation guidance to the kitchen, then dispatch the outbox."""
    from apps.notifications.services import dispatch_pending, queue_preparation_guidance

    target = dt.date.fromisoformat(today) if today else timezone.localdate()
    queued = queue_preparation_guidance(target)
    sent = dispatch_pending()
    return {"queued": queued, "sent": sent}


@shared_task(name="notifications.tasks.flag_missing_actuals")
def flag_missing_actuals(today: str | None = None) -> dict:
    from apps.notifications.services import queue_missing_actuals_reminders

    target = dt.date.fromisoformat(today) if today else timezone.localdate()
    return {"reminders": queue_missing_actuals_reminders(target)}


@shared_task(name="notifications.tasks.raise_high_waste_alerts")
def raise_high_waste_alerts(today: str | None = None) -> dict:
    from apps.notifications.services import queue_high_waste_alerts

    target = dt.date.fromisoformat(today) if today else timezone.localdate()
    return {"alerts": queue_high_waste_alerts(target)}


@shared_task(name="notifications.tasks.publish_menus")
def publish_menus(today: str | None = None) -> dict:
    from apps.menu.models import MenuSchedule
    from apps.notifications.services import queue_menu_published_notifications

    target = dt.date.fromisoformat(today) if today else timezone.localdate()
    count = MenuSchedule.objects.filter(date=target, is_published=False).update(
        is_published=True, published_at=timezone.now()
    )
    return {"published": count, "notifications": queue_menu_published_notifications(target)}
