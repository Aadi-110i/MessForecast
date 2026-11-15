"""Small helpers shared across apps."""

from __future__ import annotations

import csv
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
from io import StringIO
from typing import Iterable, Sequence

WEEKDAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def weekday_name(iso_weekday: int) -> str:
    """Monday=1 .. Sunday=7 -> readable name."""
    return WEEKDAY_NAMES[iso_weekday - 1]


def q2(value) -> Decimal:
    """Quantise to 2 decimal places using banker-safe half-up rounding."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def q3(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def largest_remainder(total: Decimal, weights: Sequence[Decimal]) -> list[int]:
    """Split ``total`` into whole units across ``weights`` without losing any.

    Uses the largest-remainder (Hare-Niemeyer) method so the parts always sum
    back to ``total`` exactly. Portions are indivisible: you cannot cook half a
    portion, so the rounding error has to land somewhere.
    """
    if not weights:
        return []
    weight_sum = sum(weights)
    if weight_sum <= 0:
        # Even split when no history tells us the preference.
        base = int(total // len(weights))
        parts = [base] * len(weights)
        for i in range(int(total - base * len(weights))):
            parts[i] += 1
        return parts

    exact = [total * w / weight_sum for w in weights]
    floors = [int(x // 1) for x in exact]
    remainder = int(total) - sum(floors)
    order = sorted(range(len(weights)), key=lambda i: exact[i] - floors[i], reverse=True)
    for k in range(remainder):
        floors[order[k % len(order)]] += 1
    return floors


def csv_response(filename: str, header: Sequence[str], rows: Iterable[Sequence]):
    """Build an HttpResponse carrying a CSV download."""
    from django.http import HttpResponse

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def week_start(value: dt.date) -> dt.date:
    """Monday of the ISO week containing ``value``."""
    return value - dt.timedelta(days=value.weekday())


def daterange(start: dt.date, end: dt.date):
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def pct(numerator, denominator) -> Decimal:
    """Percentage as Decimal; 0 when the denominator is zero."""
    denominator = Decimal(str(denominator))
    if denominator == 0:
        return Decimal("0")
    return q2(Decimal(str(numerator)) / denominator * 100)


def as_date(value):
    """Normalise a truncated value to a ``datetime.date``.

    Django's ``Trunc`` family returns a ``date`` when it truncates a
    ``DateField`` and a ``datetime`` when it truncates a ``DateTimeField``.
    Reporting code wants a date either way.
    """
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    return value
