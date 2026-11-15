"""Template context available on every page."""

from django.conf import settings

from apps.core.constants import MealType


def platform_context(request):
    return {
        "app_name": "Mess Demand Forecasting",
        "platform_short_name": "MessForecast",
        "meal_choices": MealType.choices,
        "debug": settings.DEBUG,
    }
