"""The calendar: the events that move demand.

An event is anything that changes how many people come to eat on a given
day: an examination period, a university holiday, a festival, a visiting
delegation. The forecasting engine reads them as a multiplier on the base
level, so a mis-entered event does not just fail to help - it moves every
forecast in its window.

The rules live here. The views parse and format.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.core.constants import EventType, MealType
from apps.events.models import CalendarEvent


def event_types() -> list[tuple[str, str]]:
    """Every kind of event, for the form."""
    return list(EventType.choices)


def meal_codes() -> list[str]:
    return [m.value for m in MealType]


def create_event(
    name: str,
    event_type: str,
    start_date: dt.date,
    end_date: dt.date,
    impact_factor=Decimal("1.000"),
    affects_meals: list[str] | None = None,
    affects_halls=None,
    description: str = "",
) -> CalendarEvent:
    """Add an event to the calendar."""
    event = CalendarEvent.objects.create(
        name=name.strip(),
        event_type=event_type,
        start_date=start_date,
        end_date=end_date,
        impact_factor=impact_factor,
        affects_meals=",".join(affects_meals or []),
        description=description.strip(),
    )
    if affects_halls:
        event.affects_halls.set(affects_halls)
    return event


def update_event(event: CalendarEvent, **fields) -> CalendarEvent:
    """Correct an event.

    An event that has already been forecast against is corrected rather than
    replaced. A forecast keeps its own copy of the effect it used, so the
    number that was acted on stays readable after the event is changed.
    """
    for field in ("name", "event_type", "start_date", "end_date", "impact_factor", "description"):
        if field in fields:
            value = fields[field]
            if field in ("name", "description"):
                value = value.strip()
            setattr(event, field, value)
    if "affects_meals" in fields:
        event.affects_meals = ",".join(fields["affects_meals"] or [])
    if "affects_halls" in fields:
        event.affects_halls.set(fields["affects_halls"] or [])
    event.save()
    return event


def retire_event(event: CalendarEvent) -> CalendarEvent:
    """Take an event off the calendar without losing the record.

    Retiring is the right move for an event that happened and will not
    happen again: it stops moving the forecast, and it stays on the record.
    """
    event.is_active = False
    event.save(update_fields=["is_active", "updated_at"])
    return event


def delete_event(event: CalendarEvent) -> CalendarEvent:
    """Delete an event outright.

    Nothing protects an event, because a forecast keeps its own copy of the
    effect it used rather than a link back to the event that caused it. So
    deleting one loses nothing that was already acted on.
    """
    event.delete()
    return event


def event_references(event: CalendarEvent) -> dict:
    """What still depends on an event.

    A forecast that was built with this event records the effect as a
    number, so it is listed for the reader's sake rather than as a block.
    """
    from apps.forecasting.models import Forecast

    return {
        "forecasts": Forecast.objects.filter(event_factor__gt=1).count(),
    }


def parse_meals(raw: str) -> list[str]:
    """Read a comma separated list of meal codes."""
    wanted = [part.strip().upper() for part in (raw or "").split(",") if part.strip()]
    valid = {m.value for m in MealType}
    return [w for w in wanted if w in valid]


def parse_factor(raw: str) -> Decimal:
    """Read an impact factor, refusing one that is not a number."""
    try:
        value = Decimal(str(raw).strip())
    except Exception:
        raise ValueError("The effect could not be read.")
    if value < 0:
        raise ValueError("The effect cannot be negative.")
    if value > 5:
        raise ValueError("An effect above five is a typo, not a forecast.")
    return value
