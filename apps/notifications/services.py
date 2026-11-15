"""Building and dispatching the four notification types the specification names."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models import Avg, Q
from django.utils import timezone

from apps.attendance.models import MealService
from apps.core.constants import NotificationChannel, NotificationKind
from apps.notifications.models import Notification

User = get_user_model()


def _recipients(role: str, hall=None) -> list:
    queryset = User.objects.filter(role=role, is_active=True)
    if hall is not None and role == "KITCHEN_STAFF":
        queryset = queryset.filter(Q(hall=hall) | Q(hall__isnull=True))
    return list(queryset)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def queue_preparation_guidance(target_date: dt.date) -> int:
    """Tell the kitchen what to cook for tomorrow."""
    tomorrow = target_date + dt.timedelta(days=1)
    services = MealService.objects.filter(date=tomorrow).select_related("hall")
    created = 0
    for service in services:
        plan = getattr(service, "preparation_plan", None)
        if plan is None:
            continue
        forecast = plan.forecast
        body = plan.guidance_text or (
            f"Prepare {plan.portions_to_prepare} portions for {service.get_meal_display()} "
            f"at {service.hall.name}."
        )
        for recipient in _recipients("KITCHEN_STAFF", service.hall):
            Notification.objects.create(
                kind=NotificationKind.PREPARATION_GUIDANCE,
                channel=NotificationChannel.EMAIL,
                recipient=recipient,
                role_target=recipient.role,
                hall=service.hall,
                service=service,
                subject=f"Preparation guidance: {service.hall.name} {tomorrow:%d %b} {service.get_meal_display()}",
                body=body,
                meta={
                    "portions_to_prepare": plan.portions_to_prepare,
                    "expected_attendance": str(forecast.predicted_attendance) if forecast else None,
                    "lower_bound": str(forecast.lower_bound) if forecast else None,
                    "upper_bound": str(forecast.upper_bound) if forecast else None,
                },
            )
            created += 1
    return created


def queue_missing_actuals_reminders(target_date: dt.date) -> int:
    """Remind the kitchen to record actuals for a service that has closed."""
    services = (
        MealService.objects.filter(date=target_date)
        .exclude(actual__isnull=False)
        .select_related("hall")
    )
    created = 0
    for service in services:
        if service.closes_at and timezone.now().time() < service.closes_at:
            continue
        for recipient in _recipients("KITCHEN_STAFF", service.hall):
            Notification.objects.create(
                kind=NotificationKind.MISSING_ACTUALS,
                channel=NotificationChannel.IN_APP,
                recipient=recipient,
                role_target=recipient.role,
                hall=service.hall,
                service=service,
                subject=f"Actuals not recorded: {service.hall.name} {target_date:%d %b} {service.get_meal_display()}",
                body=(
                    f"The actuals for {service.get_meal_display()} at {service.hall.name} on "
                    f"{target_date:%d %b %Y} have not been recorded yet. Please enter prepared, "
                    f"served and leftover portions so waste can be measured."
                ),
            )
            created += 1
    return created


def queue_high_waste_alerts(target_date: dt.date, threshold_pct: float = 12.0) -> int:
    """Warn the mess manager when a service wasted far more than it should."""
    from apps.waste.models import WasteRecord

    records = WasteRecord.objects.filter(service__date=target_date).select_related(
        "service", "service__hall", "dish"
    )
    by_service: dict[int, list[WasteRecord]] = {}
    for record in records:
        by_service.setdefault(record.service_id, []).append(record)

    created = 0
    for service_id, service_records in by_service.items():
        service = service_records[0].service
        forecast = getattr(service, "forecast", None)
        if forecast is None or not forecast.predicted_attendance:
            continue
        waste_portions = sum(r.leftover_portions for r in service_records)
        prepared = sum(
            d.prepared_portions for d in getattr(service, "actual").dish_actuals.all()
        ) if getattr(service, "actual", None) else 0
        if not prepared:
            continue
        waste_pct = Decimal(waste_portions) / Decimal(prepared) * 100
        if waste_pct < Decimal(str(threshold_pct)):
            continue
        waste_cost = sum((r.waste_cost for r in service_records), Decimal("0"))
        for recipient in _recipients("MESS_MANAGER"):
            Notification.objects.create(
                kind=NotificationKind.HIGH_WASTE,
                channel=NotificationChannel.IN_APP,
                recipient=recipient,
                role_target=recipient.role,
                hall=service.hall,
                service=service,
                subject=f"High waste: {service.hall.name} {target_date:%d %b} {service.get_meal_display()}",
                body=(
                    f"{waste_pct:.1f}% of what was prepared for {service.get_meal_display()} at "
                    f"{service.hall.name} on {target_date:%d %b %Y} was left over, worth "
                    f"Rs {waste_cost:,.2f}. The forecast was {forecast.predicted_attendance} portions."
                ),
                meta={"waste_pct": str(waste_pct), "waste_cost": str(waste_cost)},
            )
            created += 1
    return created


def queue_menu_published_notifications(target_date: dt.date) -> int:
    """Publish the day's menu to students."""
    from apps.menu.models import MenuSchedule

    schedules = MenuSchedule.objects.filter(date=target_date, is_published=True).select_related(
        "menu", "hall"
    )
    created = 0
    for schedule in schedules:
        dishes = schedule.menu.items_for_meal(schedule.meal)
        for recipient in _recipients("STUDENT"):
            Notification.objects.create(
                kind=NotificationKind.MENU_PUBLISHED,
                channel=NotificationChannel.IN_APP,
                recipient=recipient,
                role_target=recipient.role,
                hall=schedule.hall,
                subject=f"Menu for {target_date:%d %b %Y} - {schedule.get_meal_display()}",
                body=", ".join(item.dish.name for item in dishes),
                meta={"menu": schedule.menu.name},
            )
            created += 1
    return created


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def dispatch_pending(limit: int = 200) -> int:
    """Send queued notifications. Email uses Django's configured backend."""
    sent = 0
    pending = Notification.objects.filter(status=Notification.Status.PENDING).order_by("created_at")[:limit]
    for notification in pending:
        try:
            if notification.channel == NotificationChannel.EMAIL and notification.recipient and notification.recipient.email:
                send_mail(
                    notification.subject,
                    notification.body,
                    None,
                    [notification.recipient.email],
                    fail_silently=False,
                )
            notification.status = Notification.Status.SENT
            notification.sent_at = timezone.now()
            notification.save(update_fields=["status", "sent_at"])
            sent += 1
        except Exception as exc:  # pragma: no cover - depends on the mail backend
            notification.status = Notification.Status.FAILED
            notification.error = str(exc)
            notification.save(update_fields=["status", "error"])
    return sent
