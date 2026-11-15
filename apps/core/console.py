"""Helpers shared by the console screens.

Every console screen can be narrowed by a date window and a hall. These
helpers parse that window the same way everywhere, so a mistyped date in the
URL degrades to the default window rather than raising an error, and the
filters round-trip identically from one screen to the next.
"""

from __future__ import annotations

import datetime as dt

from django.shortcuts import get_object_or_404

from apps.catalog.models import DiningHall


def parse_date(value: str | None) -> dt.date | None:
    """Parse an ISO date, ignoring anything malformed.

    A mistyped date in the URL is a user error, not a server error, so it
    falls back to the default window rather than raising a 500.
    """
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def date_window(request, default_days: int = 28) -> tuple[dt.date, dt.date]:
    """The (start, end) window the request asks for."""
    end = parse_date(request.GET.get("end")) or dt.date.today()
    start = parse_date(request.GET.get("start")) or (end - dt.timedelta(days=default_days))
    if start > end:
        start, end = end, start
    return start, end


def selected_hall(request):
    """The hall the request asks for, or None for all halls."""
    hall_id = request.GET.get("hall")
    if not hall_id:
        return None
    return get_object_or_404(DiningHall, pk=hall_id)


def active_halls():
    return DiningHall.objects.filter(is_active=True).order_by("name")


def week_days(start: dt.date, count: int = 7) -> list[dt.date]:
    """``count`` consecutive dates from ``start``."""
    return [start + dt.timedelta(days=i) for i in range(count)]


def week_start(value: dt.date) -> dt.date:
    """Monday of the ISO week containing ``value``."""
    return value - dt.timedelta(days=value.weekday())
