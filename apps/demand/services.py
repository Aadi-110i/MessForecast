"""M4 - Historical demand analysis.

Aggregates the attendance history into the shapes the mess manager actually
asks questions about: by meal, by weekday, by exam period, by event type, and
by dish.

The specification mentions "TruncDate" (a MongoDB helper) for the Node track.
On the PostgreSQL track the equivalent is Django's ``Trunc`` family combined
with ``ExtractWeekDay``; both push the grouping into the database rather than
pulling rows into Python.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import ExtractWeekDay, TruncDate, TruncWeek

from apps.attendance.models import MealService
from apps.core.utils import as_date, weekday_name


def _weekday_label(value: int) -> str:
    """PostgreSQL ExtractWeekDay: 0 = Sunday .. 6 = Saturday."""
    return weekday_name(((value + 6) % 7) + 1)


def attendance_by_weekday(
    start: dt.date,
    end: dt.date,
    hall=None,
    meal: str | None = None,
) -> list[dict]:
    """Average attendance per weekday, ordered Monday to Sunday."""
    queryset = MealService.objects.filter(date__gte=start, date__lte=end, attendance_count__gt=0)
    if hall is not None:
        queryset = queryset.filter(hall=hall)
    if meal:
        queryset = queryset.filter(meal=meal)

    rows = (
        queryset.annotate(weekday=ExtractWeekDay("date"))
        .values("weekday")
        .annotate(
            services=Count("id"),
            total_attendance=Sum("attendance_count"),
            avg_attendance=Avg("attendance_count"),
        )
        .order_by("weekday")
    )

    buckets: dict[int, dict] = {}
    for row in rows:
        buckets[row["weekday"]] = {
            "weekday": _weekday_label(row["weekday"]),
            "services": row["services"],
            "total_attendance": int(row["total_attendance"] or 0),
            "avg_attendance": round(float(row["avg_attendance"] or 0), 1),
        }

    # Always return all seven days so a chart has a stable axis.
    return [
        buckets.get(index, {"weekday": _weekday_label(index), "services": 0, "total_attendance": 0, "avg_attendance": 0.0})
        for index in range(7)
    ]


def attendance_by_meal(
    start: dt.date, end: dt.date, hall=None
) -> list[dict]:
    """Attendance totals per meal."""
    queryset = MealService.objects.filter(date__gte=start, date__lte=end, attendance_count__gt=0)
    if hall is not None:
        queryset = queryset.filter(hall=hall)
    rows = (
        queryset.values("meal")
        .annotate(
            services=Count("id"),
            total_attendance=Sum("attendance_count"),
            avg_attendance=Avg("attendance_count"),
        )
        .order_by("meal")
    )
    return [
        {
            "meal": row["meal"],
            "services": row["services"],
            "total_attendance": int(row["total_attendance"] or 0),
            "avg_attendance": round(float(row["avg_attendance"] or 0), 1),
        }
        for row in rows
    ]


def attendance_by_week(
    start: dt.date, end: dt.date, hall=None, meal: str | None = None
) -> list[dict]:
    """Week-by-week attendance totals - the shape of demand over time."""
    queryset = MealService.objects.filter(date__gte=start, date__lte=end, attendance_count__gt=0)
    if hall is not None:
        queryset = queryset.filter(hall=hall)
    if meal:
        queryset = queryset.filter(meal=meal)
    rows = (
        queryset.annotate(week=TruncWeek("date"))
        .values("week")
        .annotate(
            services=Count("id"),
            total_attendance=Sum("attendance_count"),
            avg_attendance=Avg("attendance_count"),
        )
        .order_by("week")
    )
    return [
        {
            "week": as_date(row["week"]),
            "services": row["services"],
            "total_attendance": int(row["total_attendance"] or 0),
            "avg_attendance": round(float(row["avg_attendance"] or 0), 1),
        }
        for row in rows
    ]


def attendance_by_day(
    start: dt.date, end: dt.date, hall=None, meal: str | None = None
) -> list[dict]:
    """Daily attendance totals."""
    queryset = MealService.objects.filter(date__gte=start, date__lte=end, attendance_count__gt=0)
    if hall is not None:
        queryset = queryset.filter(hall=hall)
    if meal:
        queryset = queryset.filter(meal=meal)
    rows = (
        queryset.annotate(day=TruncDate("date"))
        .values("day")
        .annotate(services=Count("id"), total_attendance=Sum("attendance_count"))
        .order_by("day")
    )
    return [
        {
            "date": as_date(row["day"]),
            "services": row["services"],
            "total_attendance": int(row["total_attendance"] or 0),
        }
        for row in rows
    ]


def attendance_by_period(
    start: dt.date, end: dt.date, hall=None
) -> dict:
    """Compare exam periods with ordinary days.

    Exam weeks are the single biggest driver of mess attendance on a campus,
    so the analysis separates them explicitly.
    """
    from apps.events.models import CalendarEvent

    exam_windows = list(
        CalendarEvent.objects.filter(
            is_active=True, event_type="EXAM", start_date__lte=end, end_date__gte=start
        )
    )

    queryset = MealService.objects.filter(date__gte=start, date__lte=end, attendance_count__gt=0)
    if hall is not None:
        queryset = queryset.filter(hall=hall)

    exam_total = 0
    exam_services = 0
    normal_total = 0
    normal_services = 0
    for service in queryset.only("date", "attendance_count"):
        is_exam = any(event.covers(service.date) for event in exam_windows)
        if is_exam:
            exam_total += service.attendance_count
            exam_services += 1
        else:
            normal_total += service.attendance_count
            normal_services += 1

    exam_avg = (exam_total / exam_services) if exam_services else 0
    normal_avg = (normal_total / normal_services) if normal_services else 0
    lift = ((exam_avg - normal_avg) / normal_avg * 100) if normal_avg else 0

    return {
        "exam_services": exam_services,
        "exam_total": exam_total,
        "exam_avg": round(exam_avg, 1),
        "normal_services": normal_services,
        "normal_total": normal_total,
        "normal_avg": round(normal_avg, 1),
        "exam_lift_pct": round(lift, 1),
    }


def dish_demand(start: dt.date, end: dt.date, hall=None) -> list[dict]:
    """How many portions of each dish were actually served.

    Dish-level demand cannot come from the attendance scan (a scan records that
    a student came, not what they ate), so it is measured from the post-service
    actuals, which record what was served and what was left over.
    """
    from apps.actuals.models import DishActual, ServiceActual

    queryset = ServiceActual.objects.filter(
        service__date__gte=start, service__date__lte=end
    )
    if hall is not None:
        queryset = queryset.filter(service__hall=hall)

    rows = (
        DishActual.objects.filter(service_actual__in=queryset)
        .values("dish__name", "dish__code")
        .annotate(
            served=Sum("served_portions"),
            prepared=Sum("prepared_portions"),
            leftover=Sum("leftover_portions"),
            services=Count("id"),
        )
        .order_by("-served")
    )
    return [
        {
            "dish": row["dish__name"],
            "code": row["dish__code"],
            "services": row["services"],
            "prepared_portions": int(row["prepared"] or 0),
            "served_portions": int(row["served"] or 0),
            "leftover_portions": int(row["leftover"] or 0),
        }
        for row in rows
    ]


def attendance_summary(start: dt.date, end: dt.date, hall=None) -> dict:
    """Headline numbers for the dashboard."""
    queryset = MealService.objects.filter(date__gte=start, date__lte=end)
    if hall is not None:
        queryset = queryset.filter(hall=hall)
    totals = queryset.aggregate(
        services=Count("id"),
        attendance=Sum("attendance_count"),
        avg=Avg("attendance_count"),
        registered=Sum("registered_strength"),
    )
    attendance = int(totals["attendance"] or 0)
    registered = int(totals["registered"] or 0)
    return {
        "services": totals["services"] or 0,
        "total_attendance": attendance,
        "avg_attendance": round(float(totals["avg"] or 0), 1),
        "registered_strength": registered,
        "attendance_rate_pct": round(attendance / registered * 100, 1) if registered else 0.0,
    }
