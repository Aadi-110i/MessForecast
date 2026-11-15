"""Shared domain vocabulary.

These choices are referenced by every app, so they live in ``core`` to avoid
circular imports between the domain apps.
"""

from django.db import models


class MealType(models.TextChoices):
    BREAKFAST = "BREAKFAST", "Breakfast"
    LUNCH = "LUNCH", "Lunch"
    DINNER = "DINNER", "Dinner"
    SNACK = "SNACK", "Snack"


class CaptureMethod(models.TextChoices):
    QR = "QR", "QR scan"
    RFID = "RFID", "RFID tap"
    MANUAL = "MANUAL", "Manual entry"


class EventType(models.TextChoices):
    EXAM = "EXAM", "Examination period"
    FEST = "FEST", "Festival / cultural event"
    HOLIDAY = "HOLIDAY", "Holiday"
    VACATION = "VACATION", "Vacation / term break"
    SPORTS = "SPORTS", "Sports day"
    GUEST = "GUEST", "Guest / workshop attendance"
    OTHER = "OTHER", "Other event"


class PrepMode(models.TextChoices):
    """How the quantity prepared for a service was decided.

    ``REGISTERED_STRENGTH`` is the pre-project practice this platform replaces.
    ``FORECAST_GUIDED`` is the practice the forecasting engine drives.
    """

    REGISTERED_STRENGTH = "REGISTERED_STRENGTH", "Prepared against registered strength"
    FORECAST_GUIDED = "FORECAST_GUIDED", "Prepared against the forecast"


class WasteCause(models.TextChoices):
    OVER_PREPARATION = "OVER_PREPARATION", "Over-preparation"
    QUALITY = "QUALITY", "Quality rejection"
    SPOILAGE = "SPOILAGE", "Spoilage"
    OVERSERVED = "OVERSERVED", "Taken but not eaten"
    UNCLASSIFIED = "UNCLASSIFIED", "Unclassified"


class NotificationKind(models.TextChoices):
    PREPARATION_GUIDANCE = "PREPARATION_GUIDANCE", "Daily preparation guidance"
    MISSING_ACTUALS = "MISSING_ACTUALS", "Missing actuals reminder"
    HIGH_WASTE = "HIGH_WASTE", "High waste alert"
    MENU_PUBLISHED = "MENU_PUBLISHED", "Menu published to students"
    FORECAST_READY = "FORECAST_READY", "Forecast ready"


class NotificationChannel(models.TextChoices):
    EMAIL = "EMAIL", "Email"
    SMS = "SMS", "SMS"
    IN_APP = "IN_APP", "In-app"


#: Mapping of meal service -> the local time the service is served. Used to pick
#: the right pre-service snapshot when the kitchen asks "what should I cook today?".
MEAL_SERVICE_ORDER = {
    MealType.BREAKFAST: 0,
    MealType.LUNCH: 1,
    MealType.DINNER: 2,
    MealType.SNACK: 3,
}
