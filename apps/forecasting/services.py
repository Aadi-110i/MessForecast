"""Database-facing layer for the forecasting engine (M5).

``apps.forecasting.engine`` does the arithmetic. This module feeds it history
from PostgreSQL and writes the result back, so the engine stays testable and
the upgrade path (a learned model in a second service) stays open.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.attendance.models import MealService
from apps.catalog.models import DiningHall
from apps.events.models import CalendarEvent
from apps.forecasting.engine import (
    BaselineForecaster,
    ForecastResult,
    Observation,
)
from apps.forecasting.models import Forecast


@dataclass
class EventCalendar:
    """The events that apply to one hall, with a per-date multiplier.

    Holding this in memory for the duration of a forecasting run avoids
    re-querying the calendar for every date. The hall scope of each event is
    resolved once here rather than on every lookup.
    """

    events: list[CalendarEvent] = field(default_factory=list)

    def __post_init__(self):
        self._hall_scopes: dict[int, set[int] | None] = {}
        for event in self.events:
            # ``None`` means the event applies to every hall.
            ids = {hall_id for hall_id in event.affects_halls.values_list("id", flat=True)}
            self._hall_scopes[event.id] = ids or None

    def factor(self, on_date: dt.date, meal: str, hall) -> tuple[Decimal, list[str]]:
        """Combined multiplier for a date, and the names responsible for it."""
        combined = Decimal("1")
        names: list[str] = []
        for event in self.events:
            if not event.is_active or not event.covers(on_date):
                continue
            scope = self._hall_scopes.get(event.id)
            if scope is not None and hall is not None and hall.pk not in scope:
                continue
            if not event.applies_to_meal(meal):
                continue
            factor = event.impact_factor
            if factor != Decimal("1"):
                combined *= factor
                names.append(event.name)
        return combined, names

    def is_exam(self, on_date: dt.date, hall) -> bool:
        for event in self.events:
            if event.is_active and event.covers(on_date) and event.event_type == "EXAM":
                return True
        return False


@dataclass
class ServiceHistory:
    """Observations for one (hall, meal) plus the calendar that shaped them."""

    hall: DiningHall
    meal: str
    observations: list[Observation]
    event_calendar: EventCalendar

    def latest_date(self) -> dt.date | None:
        return self.observations[-1].date if self.observations else None


def build_event_calendar(
    start: dt.date, end: dt.date, hall: DiningHall | None = None
) -> EventCalendar:
    """Load every event overlapping the window that applies to ``hall``."""
    queryset = CalendarEvent.objects.filter(
        is_active=True, start_date__lte=end, end_date__gte=start
    ).prefetch_related("affects_halls")
    if hall is not None:
        queryset = queryset.filter(Q(affects_halls__isnull=True) | Q(affects_halls=hall)).distinct()
    return EventCalendar(list(queryset))


def build_history(
    hall: DiningHall,
    meal: str,
    until: dt.date,
    lookback_weeks: int | None = None,
    event_calendar: EventCalendar | None = None,
) -> ServiceHistory:
    """Collect the historical observations for one hall and meal."""
    lookback_weeks = lookback_weeks or getattr(settings, "FORECAST_LOOKBACK_WEEKS", 8)
    start = until - dt.timedelta(weeks=lookback_weeks)

    services = (
        MealService.objects.filter(
            hall=hall,
            meal=meal,
            date__gte=start,
            date__lt=until,
        )
        .order_by("date")
        .only("date", "attendance_count")
    )

    if event_calendar is None:
        event_calendar = build_event_calendar(start, until, hall)

    observations: list[Observation] = []
    for service in services:
        if service.attendance_count <= 0:
            # A service with nobody recorded tells us nothing about demand and
            # would drag the average towards zero.
            continue
        factor, _names = event_calendar.factor(service.date, meal, hall)
        observations.append(
            Observation(
                date=service.date,
                attendance=service.attendance_count,
                event_factor=factor,
                is_exam_period=event_calendar.is_exam(service.date, hall),
            )
        )
    return ServiceHistory(hall=hall, meal=meal, observations=observations, event_calendar=event_calendar)


def get_forecaster() -> BaselineForecaster:
    return BaselineForecaster(
        confidence=float(getattr(settings, "FORECAST_CONFIDENCE_LEVEL", 0.80)),
        min_history=int(getattr(settings, "FORECAST_MIN_OBSERVATIONS", 6)),
    )


def _meal_label(meal: str) -> str:
    return {"BREAKFAST": "Breakfast", "LUNCH": "Lunch", "DINNER": "Dinner", "SNACK": "Snack"}.get(
        meal, meal.title()
    )


def forecast_service(
    service: MealService,
    forecaster: BaselineForecaster | None = None,
    history: ServiceHistory | None = None,
    persist: bool = True,
) -> ForecastResult:
    """Produce (and by default store) the forecast for one meal service."""
    forecaster = forecaster or get_forecaster()
    hall = service.hall

    if history is None:
        history = build_history(hall, service.meal, service.date)

    factor, event_names = history.event_calendar.factor(service.date, service.meal, hall)
    context = {
        "hall_name": hall.name,
        "meal_label": _meal_label(service.meal),
        "event_names": ", ".join(event_names),
    }

    fallback_rate = _hall_attendance_rate(hall, service.meal, service.date)
    result = forecaster.predict(
        history.observations,
        target_date=service.date,
        target_event_factor=factor,
        registered_strength=service.registered_strength,
        fallback_attendance_rate=fallback_rate,
        context=context,
    )

    if persist:
        forecast_object, _created = Forecast.objects.update_or_create(
            service=service,
            defaults={
                "method": result.method,
                "model_version": result.model_version,
                "horizon_days": int(getattr(settings, "FORECAST_HORIZON_DAYS", 7)),
                "predicted_attendance": result.point_estimate,
                "lower_bound": result.lower_bound,
                "upper_bound": result.upper_bound,
                "confidence_level": Decimal(str(result.confidence_level)),
                "base_level": result.base_level,
                "weekday_factor": result.weekday_factor,
                "event_factor": result.event_factor,
                "trend_pct": result.trend_pct,
                "rmse": result.rmse,
                "mape": result.mape,
                "input_signature": result.input_signature,
                "explanation": result.explanation,
                "is_fallback": result.fallback_used,
                "observations_used": result.observations_used,
                "context": {**context, "event_names": event_names},
            },
        )
        # Populate the reverse relation so the caller does not have to query
        # for the forecast it has just caused to be written.
        service.forecast = forecast_object
    return result


def _hall_attendance_rate(hall: DiningHall, meal: str, on_date: dt.date) -> Decimal | None:
    """Share of registered strength that typically turns up, for cold starts."""
    recent = (
        MealService.objects.filter(hall=hall, meal=meal, date__lt=on_date)
        .exclude(registered_strength=0)
        .order_by("-date")[:10]
    )
    totals = [s for s in recent if s.attendance_count > 0]
    if not totals:
        return None
    rate = sum(
        (Decimal(s.attendance_count) / Decimal(s.registered_strength) for s in totals), Decimal("0")
    ) / Decimal(len(totals))
    return min(rate, Decimal("1"))


def forecast_services(services, forecaster: BaselineForecaster | None = None) -> list[ForecastResult]:
    """Forecast a list of services, grouping the work by hall and meal.

    Grouping matters: the same (hall, meal) history is reused for every date
    in the batch instead of being rebuilt per service.
    """
    forecaster = forecaster or get_forecaster()
    results: list[ForecastResult] = []

    grouped: dict[tuple[int, str], list[MealService]] = {}
    for service in services:
        grouped.setdefault((service.hall_id, service.meal), []).append(service)

    for (hall_id, meal), group in grouped.items():
        group.sort(key=lambda s: s.date)
        hall = group[0].hall
        calendar = build_event_calendar(
            min(s.date for s in group) - dt.timedelta(weeks=20), max(s.date for s in group), hall
        )
        for service in group:
            history = build_history(hall, meal, service.date, event_calendar=calendar)
            results.append(forecast_service(service, forecaster, history=history))
    return results


def generate_forecasts_for_range(
    start: dt.date,
    end: dt.date,
    forecaster: BaselineForecaster | None = None,
) -> list[ForecastResult]:
    """Forecast every scheduled service between ``start`` and ``end``.

    This is the daily job: the specification asks for a 7-day forecast
    produced every day.
    """
    services = list(
        MealService.objects.filter(date__gte=start, date__lte=end).select_related("hall")
    )
    return forecast_services(services, forecaster)


def refresh_forecast_for_service(service: MealService) -> Forecast | None:
    """Recompute and store the forecast for one service."""
    forecast_service(service)
    return getattr(service, "forecast", None)
