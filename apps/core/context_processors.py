"""Template context available on every page."""

from django.conf import settings

from apps.core.constants import MealType


def platform_context(request):
    context = {
        "app_name": "Mess Demand Forecasting",
        "platform_short_name": "MessForecast",
        "meal_choices": MealType.choices,
        "debug": settings.DEBUG,
    }
    context.update(_pass_figures(request))
    return context


def _pass_figures(request):
    """The two figures carried on the access pass of the sign-in screen.

    They are read from the records rather than typed into the template, so
    the pass says something true about the platform it opens. The queries run
    only for the two screens that show the pass, and nowhere else.
    """
    path = getattr(request, "path", "") or ""
    if not (path.startswith("/accounts/login") or path.startswith("/accounts/register")):
        return {}

    import datetime as dt

    from django.utils import timezone

    from apps.attendance.models import MealService
    from apps.actuals.models import ServiceActual
    from apps.forecasting.models import Forecast

    today = timezone.localdate()

    # The next service that has a forecast on it, or the registered strength
    # if the forecaster has not reached it yet.
    expected = None
    service = MealService.objects.filter(date__gte=today).order_by("date", "meal").first()
    if service is not None:
        forecast = Forecast.objects.filter(service=service).first()
        if forecast is not None:
            expected = int(round(float(forecast.predicted_attendance)))
        else:
            expected = int(service.registered_strength)

    # What was actually left over over the last fortnight.
    window = today - dt.timedelta(days=14)
    rows = ServiceActual.objects.filter(service__date__gte=window).values_list(
        "prepared_portions_total", "leftover_portions_total"
    )
    prepared = 0
    leftover = 0
    for prepared_row, leftover_row in rows:
        prepared += prepared_row
        leftover += leftover_row
    waste_pct = round(leftover / prepared * 100, 1) if prepared else None

    return {"auth_expected_turnout": expected, "auth_waste_pct": waste_pct}
