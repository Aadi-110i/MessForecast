"""HTML surfaces: the admin dashboard and the tablet kitchen screen."""

from __future__ import annotations

import datetime as dt

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.accounts.permissions import has_capability
from apps.accounts.models import User
from apps.actuals.models import ServiceActual
from apps.attendance.models import AttendanceRecord, MealService
from apps.catalog.models import CostRate, DiningHall
from apps.core.constants import MEAL_SERVICE_ORDER, MealType
from apps.core.decorators import requires
from apps.core import utils as core_utils
from apps.core.utils import csv_response
from apps.demand import services as demand_services
from apps.events.models import ServiceLevelConfig
from apps.forecasting.models import Forecast
from apps.menu.models import MenuSchedule
from apps.notifications.models import Notification
from apps.planning.models import PreparationPlan
from apps.planning.services import indent_csv_rows
from apps.reporting import services as reporting
from apps.waste import services as waste_services


def _range_from_request(request, default_days: int = 28) -> tuple[dt.date, dt.date]:
    today = timezone.localdate()
    end = _parse_date(request.GET.get("end"), "end") or today
    start = (
        _parse_date(request.GET.get("start"), "start")
        or end - dt.timedelta(days=default_days)
    )
    return start, end


def _parse_date(value: str | None, field: str) -> dt.date | None:
    """Parse an ISO date from the query string, ignoring anything malformed.

    A mistyped date in the URL is a user error, not a server error, so it
    falls back to the default window rather than raising a 500.
    """
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _selected_hall(request):
    hall_id = request.GET.get("hall")
    if not hall_id:
        return None
    return get_object_or_404(DiningHall, pk=hall_id)


def _maybe(obj, name: str):
    """A reverse one-to-one that may not exist.

    ``service.forecast`` raises ``DoesNotExist`` when the service has no
    forecast. A template swallows that and treats it as missing; Python does
    not, so every one of these is read through here.
    """
    try:
        return getattr(obj, name)
    except ObjectDoesNotExist:
        return None


@login_required
@require_GET
def dashboard_home(request):
    """Route every role to the dashboard it is allowed to use.

    Students and kitchen staff do not belong in the mess manager's console;
    they land on their own surface. Everyone else reaches the operational
    overview, which is capability-gated.
    """
    user = request.user
    if user.role == User.Role.STUDENT:
        return redirect("dashboard-student")
    if user.role == User.Role.KITCHEN_STAFF:
        return redirect("kitchen-dashboard")
    if user.role == User.Role.FINANCE_OFFICER:
        return redirect("dashboard-finance")
    if not has_capability(user, "VIEW_MENU"):
        return JsonResponse({"detail": "Not permitted"}, status=403)

    start, end = _range_from_request(request)
    hall = _selected_hall(request)
    today = timezone.localdate()

    accuracy = reporting.accuracy_summary(start, end, hall)
    savings = None
    baseline_window = request.GET.get("baseline_start")
    if baseline_window:
        baseline_start = dt.date.fromisoformat(baseline_window)
        baseline_end = dt.date.fromisoformat(request.GET.get("baseline_end", baseline_window.isoformat()))
        savings = reporting.baseline_comparison(baseline_start, baseline_end, start, end, hall)

    todays_services = (
        MealService.objects.filter(date=today)
        .select_related("hall")
        .prefetch_related("forecast", "preparation_plan", "actual")
    )

    waste_totals = waste_services.waste_totals(start, end, hall)
    demand_summary = demand_services.attendance_summary(start, end, hall)
    period = demand_services.attendance_by_period(start, end, hall)

    # Today's services, grouped by meal, so the manager reads the day as three
    # beats instead of a row per hall and meal.
    today_meals: list[dict] = []
    by_meal: dict[str, dict] = {}
    for service in todays_services:
        entry = by_meal.setdefault(
            service.meal,
            {
                "meal": service.meal,
                "label": service.get_meal_display(),
                "time": MEAL_TIMES.get(service.meal, {}).get("time", ""),
                "expected": 0,
                "turned_up": 0,
                "forecast": 0,
                "forecasted": 0,
                "cooked": 0,
                "leftover": 0,
                "recorded": 0,
                "services": 0,
                "in_range": 0,
                "out_of_range": 0,
                "unwritten": 0,
                "state": "later",
            },
        )
        entry["services"] += 1
        entry["expected"] += service.registered_strength
        entry["turned_up"] += service.attendance_count
        forecast = _maybe(service, "forecast")
        plan = _maybe(service, "preparation_plan")
        actual = _maybe(service, "actual")
        if forecast is not None:
            entry["forecast"] += int(forecast.predicted_attendance)
            entry["forecasted"] += 1
        if plan is not None:
            entry["cooked"] += plan.portions_to_prepare
        if actual is not None:
            entry["leftover"] += actual.leftover_portions_total
            entry["recorded"] += 1
        else:
            entry["unwritten"] += 1
        if forecast is not None and service.attendance_count:
            if service.attendance_count >= forecast.lower_bound and service.attendance_count <= forecast.upper_bound:
                entry["in_range"] += 1
            else:
                entry["out_of_range"] += 1
    for entry in by_meal.values():
        entry["state"] = _meal_state(entry["meal"], timezone.localtime())
        entry["delta"] = entry["turned_up"] - entry["forecast"] if entry["forecasted"] else 0
        today_meals.append(entry)
    today_meals.sort(key=lambda e: MEAL_SERVICE_ORDER.get(e["meal"], 9))

    day_expected = sum(e["expected"] for e in today_meals)
    day_turned_up = sum(e["turned_up"] for e in today_meals)
    day_forecast = sum(e["forecast"] for e in today_meals)
    next_meal = next((e for e in today_meals if e["state"] == "later"), None)
    served_meals = [e for e in today_meals if e["state"] != "later"]
    # A meal that has run but has not been written up says nothing about the
    # students, and must not be reported as though they had not come.
    unwritten_meals = [e for e in served_meals if e["recorded"] == 0]
    written_meals = [e for e in served_meals if e["recorded"] > 0]

    # Waste by dish, each with its picture, so the manager sees which food is
    # throwing the money away rather than reading a rank column.
    top_dishes = waste_services.top_waste_dishes(start, end, hall, limit=10)
    for dish in top_dishes:
        dish["slug"] = core_utils.dish_art_slug_for(dish.get("code", ""), dish.get("dish", ""))
        dish["cost_label"] = f"₹{dish['waste_cost']:,.0f}"

    # The causes of the waste, each with its share of the money.
    waste_by_cause = waste_services.waste_by_cause(start, end, hall)
    for cause in waste_by_cause:
        cause["cost_label"] = f"₹{cause['waste_cost']:,.0f}"

    context = {
        "start": start,
        "end": end,
        "hall": hall,
        "halls": DiningHall.objects.filter(is_active=True),
        "accuracy": accuracy,
        "savings": savings,
        "waste_totals": waste_totals,
        "waste_cost_label": f"₹{waste_totals['waste_cost']:,.0f}",
        "waste_by_week": waste_services.waste_by_week(start, end, hall),
        "waste_by_cause": waste_by_cause,
        "top_dishes": top_dishes,
        "mape_over_time": reporting.mape_over_time(start, end, hall),
        "todays_services": todays_services,
        "today_meals": today_meals,
        "day_expected": day_expected,
        "day_turned_up": day_turned_up,
        "day_forecast": day_forecast,
        "next_meal": next_meal,
        "served_meals": served_meals,
        "unwritten_meals": unwritten_meals,
        "written_meals": written_meals,
        "weekday_pattern": demand_services.attendance_by_weekday(start, end, hall),
        "period": demand_services.attendance_by_period(start, end, hall),
        "demand_summary": demand_summary,
        # The exam lift is a forecast input, not a headline: it belongs in the
        # period summary rather than on the front of the page.
        "exam_lift_pct": period["exam_lift_pct"],
    }
    return render(request, "dashboard/home.html", context)


@login_required
@requires("VIEW_WASTE_COST")
@require_GET
def dashboard_waste(request):
    """Waste quantity and cost by dish, meal, hall and period."""
    start, end = _range_from_request(request)
    hall = _selected_hall(request)

    totals = waste_services.waste_totals(start, end, hall)
    by_cause = waste_services.waste_by_cause(start, end, hall)
    cause_label = by_cause[0]["label"] if by_cause else "None recorded"
    cause_note = (
        f"{by_cause[0]['records']} records, ₹{by_cause[0]['waste_cost']:,.0f}"
        if by_cause
        else "No waste has been classified yet"
    )
    context = {
        "start": start,
        "end": end,
        "hall": hall,
        "halls": DiningHall.objects.filter(is_active=True),
        "totals": totals,
        "by_week": waste_services.waste_by_week(start, end, hall),
        "by_meal": waste_services.waste_by_meal(start, end, hall),
        "by_hall": waste_services.waste_by_hall(start, end),
        "by_cause": waste_services.waste_by_cause(start, end, hall),
        "top_dishes": waste_services.top_waste_dishes(start, end, hall, limit=10),
        "figures": [
            {
                "label": "Cost of waste",
                "value": f"₹{totals['waste_cost']:,.0f}",
                "note": f"Across {totals['records']} dish records",
                "tone": "loss",
            },
            {
                "label": "Weight thrown away",
                "value": f"{totals['waste_quantity_kg']:,.1f} kg",
                "note": "Portions left times the standard portion size",
            },
            {
                "label": "Cost per service",
                "value": f"₹{totals['waste_cost'] / totals['records']:,.0f}" if totals["records"] else "₹0",
                "note": "The mean across the period",
            },
            {
                "label": "Biggest cause",
                "value": cause_label,
                "note": cause_note,
                "tone": "loss",
                "kind": "text",
            },
        ],
    }
    return render(request, "dashboard/waste.html", context)


@login_required
@requires("VIEW_ACCURACY")
@require_GET
def dashboard_accuracy(request):
    """Forecast accuracy (MAPE) by meal, hall and week."""
    start, end = _range_from_request(request)
    hall = _selected_hall(request)

    context = {
        "start": start,
        "end": end,
        "hall": hall,
        "halls": DiningHall.objects.filter(is_active=True),
        "summary": reporting.accuracy_summary(start, end, hall),
        "exact_mape": reporting.exact_mape(start, end, hall),
        "by_meal_and_hall": reporting.mape_by_meal_and_hall(start, end),
        "over_time": reporting.mape_over_time(start, end, hall),
        "rows": reporting.forecast_vs_actual_rows(start, end, hall, limit=200),
    }
    return render(request, "dashboard/accuracy.html", context)


@login_required
@requires("VIEW_PREPARATION_PLAN")
@require_GET
def dashboard_planning(request):
    """Preparation plans and ingredient indents.

    A manager works the week ahead, so upcoming plans come first by
    default. The page shows the next few in full rather than every plan
    in the window, because a hundred plans is a hundred screens.
    """
    start, end = _range_from_request(request)
    hall = _selected_hall(request)

    plans = PreparationPlan.objects.filter(service__date__gte=start, service__date__lte=end)
    if hall is not None:
        plans = plans.filter(service__hall=hall)
    plans = plans.select_related("service", "service__hall", "forecast").prefetch_related("lines__dish")

    today = timezone.localdate()
    when = request.GET.get("when") or "upcoming"
    if when == "past":
        ordered = plans.filter(service__date__lt=today).order_by("-service__date", "service__meal")
    else:
        ordered = plans.filter(service__date__gte=today).order_by("service__date", "service__meal")

    shown = list(ordered[:12])

    context = {
        "start": start,
        "end": end,
        "hall": hall,
        "halls": DiningHall.objects.filter(is_active=True),
        "plans": shown,
        "when": when,
        "today": today,
        "total_plans": plans.count(),
        "upcoming_count": plans.filter(service__date__gte=today).count(),
        "past_count": plans.filter(service__date__lt=today).count(),
    }
    return render(request, "dashboard/planning.html", context)


@login_required
@require_GET
def export_indent_csv(request, plan_id: int):
    """Download the ingredient indent in the procurement format."""
    plan = get_object_or_404(PreparationPlan.objects.select_related("service"), pk=plan_id)
    indent = getattr(plan, "indent", None)
    if indent is None:
        return JsonResponse({"detail": "No indent for this plan"}, status=404)
    header, rows = indent_csv_rows(indent)
    return csv_response(f"indent_{indent.hall.code}_{indent.date.isoformat()}.csv", header, rows)


# ---------------------------------------------------------------------------
# Kitchen screen (tablet-first)
# ---------------------------------------------------------------------------

@login_required
@require_GET
def kitchen_dashboard(request):
    """The tablet home: today's services and what each one still needs.

    Three decisions on one screen. Which service is next, how much to cook,
    and whether it has been written up. Everything is a tap.
    """
    if not (
        has_capability(request.user, "RECORD_ACTUALS")
        or has_capability(request.user, "VIEW_PREPARATION_PLAN")
    ):
        return JsonResponse({"detail": "Not permitted"}, status=403)

    today = timezone.localdate()
    services = (
        MealService.objects.filter(date=today)
        .select_related("hall", "forecast", "preparation_plan", "actual")
        .order_by("meal", "hall__code")
    )
    if request.user.role == "KITCHEN_STAFF" and request.user.hall_id:
        services = services.filter(hall_id=request.user.hall_id)

    rows = []
    for service in services:
        plan = getattr(service, "preparation_plan", None)
        actual = getattr(service, "actual", None)
        forecast = getattr(service, "forecast", None)
        if actual is not None:
            state = "done"
            state_label = "Written up"
        elif plan is not None:
            state = "ready"
            state_label = "Ready to cook"
        else:
            state = "waiting"
            state_label = "No plan yet"
        rows.append(
            {
                "service": service,
                "plan": plan,
                "actual": actual,
                "forecast": forecast,
                "state": state,
                "state_label": state_label,
                "turnout": service.attendance_count,
                "target": plan.portions_to_prepare if plan else None,
                "leftover": actual.leftover_portions_total if actual else None,
            }
        )

    outstanding = sum(1 for r in rows if r["state"] != "done")
    to_prepare = sum(r["target"] for r in rows if r["target"])
    turnout = sum(r["turnout"] for r in rows)
    leftover = sum(r["leftover"] for r in rows if r["leftover"] is not None)

    context = {
        "today": today,
        "rows": rows,
        "halls": DiningHall.objects.filter(is_active=True),
        "totals": {
            "services": len(rows),
            "outstanding": outstanding,
            "to_prepare": to_prepare,
            "turnout": turnout,
            "leftover": leftover,
        },
    }
    return render(request, "kitchen/dashboard.html", context)


@login_required
@require_GET
def kitchen_actuals(request, service_id: int):
    """Record what was prepared and served for one service.

    The big-button screen: large touch targets, high contrast, and no
    navigation that a gloved hand can get wrong.
    """
    if not (
        has_capability(request.user, "RECORD_ACTUALS")
        or has_capability(request.user, "VIEW_PREPARATION_PLAN")
    ):
        return JsonResponse({"detail": "Not permitted"}, status=403)

    today = timezone.localdate()
    service = get_object_or_404(
        MealService.objects.select_related("hall"), pk=service_id
    )
    plan = getattr(service, "preparation_plan", None)
    actual = getattr(service, "actual", None)

    context = {
        "today": today,
        "service": service,
        "plan": plan,
        "actual": actual,
        "plan_lines": plan.lines.select_related("dish").order_by("-portions") if plan else [],
        "actual_lines": actual.dish_actuals.select_related("dish").order_by("dish__name") if actual else [],
        "indent": getattr(plan, "indent", None) if plan else None,
    }
    return render(request, "kitchen/screen.html", context)


@login_required
@requires("RECORD_ACTUALS", "VIEW_PREPARATION_PLAN")
@require_GET
def kitchen_guidance(request, service_id: int):
    """The preparation brief for one service, as JSON for the kitchen screen."""
    service = get_object_or_404(MealService.objects.select_related("hall"), pk=service_id)
    plan = getattr(service, "preparation_plan", None)
    forecast = getattr(service, "forecast", None)
    indent = getattr(plan, "indent", None) if plan else None

    return JsonResponse(
        {
            "service": {
                "id": service.id,
                "hall": service.hall.name,
                "date": service.date.isoformat(),
                "meal": service.meal,
                "meal_display": service.get_meal_display(),
            },
            "forecast": {
                "predicted": str(forecast.predicted_attendance),
                "lower": str(forecast.lower_bound),
                "upper": str(forecast.upper_bound),
                "explanation": forecast.explanation,
            }
            if forecast
            else None,
            "plan": {
                "portions_to_prepare": plan.portions_to_prepare,
                "safety_margin_pct": str(plan.safety_margin_pct),
                "estimated_cost": str(plan.estimated_cost),
                "guidance_text": plan.guidance_text,
                "lines": [
                    {
                        "dish": line.dish.name,
                        "dish_id": line.dish_id,
                        "portions": line.portions,
                        "estimated_cost": str(line.estimated_cost),
                    }
                    for line in plan.lines.select_related("dish")
                ],
            }
            if plan
            else None,
            "indent": {
                "total_cost": str(indent.total_estimated_cost),
                "procurement_text": indent.procurement_text,
                "lines": [
                    {
                        "ingredient": line.ingredient.name,
                        "quantity": str(line.quantity),
                        "unit": line.unit,
                        "packs": str(line.packs),
                        "estimated_cost": str(line.estimated_cost),
                    }
                    for line in indent.lines.select_related("ingredient")
                ],
            }
            if indent
            else None,
        }
    )


@login_required
@requires("VIEW_WASTE_COST", "RECORD_ACTUALS")
@require_GET
def data_quality_monitor(request):
    """Services that are missing actuals - the data-quality panel in the spec."""
    start, end = _range_from_request(request, default_days=14)
    missing = (
        MealService.objects.filter(date__gte=start, date__lte=end, actual__isnull=True)
        .select_related("hall")
        .order_by("date", "meal")
    )
    recorded = ServiceActual.objects.filter(service__date__gte=start, service__date__lte=end).count()
    total = MealService.objects.filter(date__gte=start, date__lte=end).count()

    context = {
        "start": start,
        "end": end,
        "missing": missing,
        "recorded": recorded,
        "total": total,
        "completion_pct": round(recorded / total * 100, 1) if total else 0.0,
        "level_configs": ServiceLevelConfig.objects.all().select_related("hall"),
        "forecast_count": Forecast.objects.filter(service__date__gte=start, service__date__lte=end).count(),
    }
    return render(request, "dashboard/data_quality.html", context)


# ---------------------------------------------------------------------------
# Role-specific dashboards
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# The student surface
# ---------------------------------------------------------------------------

#: When each meal is served, and the window in which it counts as "on the
#: counter". A student wants to know whether they have missed it yet.
MEAL_TIMES = {
    MealType.BREAKFAST: {"label": "Breakfast", "time": "8:00 AM", "start": (7, 0), "end": (9, 45)},
    MealType.LUNCH: {"label": "Lunch", "time": "1:00 PM", "start": (12, 0), "end": (14, 45)},
    MealType.DINNER: {"label": "Dinner", "time": "7:00 PM", "start": (18, 30), "end": (21, 0)},
}


def _meal_state(meal: str, when: dt.datetime | None = None) -> str:
    """``served``, ``now`` or ``later`` for one meal."""
    spec = MEAL_TIMES.get(meal)
    if spec is None:
        return "later"
    moment = when or timezone.localtime()
    minutes = moment.hour * 60 + moment.minute
    start = spec["start"][0] * 60 + spec["start"][1]
    end = spec["end"][0] * 60 + spec["end"][1]
    if minutes >= end:
        return "served"
    if minutes >= start:
        return "now"
    return "later"


#: How a dish category is written on the menu, in the words a menu uses.
DISH_KINDS = {
    "VEG": "Vegetable",
    "NONVEG": "Non-veg",
    "STAPLE": "Staple",
    "DAAL": "Daal",
    "SALAD": "Fresh",
    "BEVERAGE": "To drink",
    "SWEET": "Sweet",
}


def _dish_cards(items) -> list[dict]:
    """Menu rows turned into the small dictionaries the menu template draws."""
    cards = []
    for item in items:
        dish = item.dish
        cards.append(
            {
                "name": dish.name,
                "slug": core_utils.dish_art_slug(dish),
                "category": dish.category,
                "kind": DISH_KINDS.get(dish.category, "Dish"),
                "is_veg": dish.category == "VEG",
                "is_nonveg": dish.category == "NONVEG",
            }
        )
    return cards


def _meal_entry(meal: str) -> dict:
    spec = MEAL_TIMES.get(meal, {})
    return {
        "meal": meal,
        "label": spec.get("label", meal.title()),
        "time": spec.get("time", ""),
        "halls": [],
        "dishes": [],
        "seen": set(),
    }


def _menus_by_date(schedules) -> dict:
    """Group published schedule rows by date, then by meal.

    Both halls usually cook the same menu, so the dishes are collected once
    and the halls that serve them are listed beside them. The whole week is
    read in one query and grouped in Python, because a student opening this
    on a phone should not wait for fourteen round trips.
    """
    by_date: dict[dt.date, dict[str, dict]] = {}
    for schedule in schedules:
        meals = by_date.setdefault(schedule.date, {})
        entry = meals.setdefault(schedule.meal, _meal_entry(schedule.meal))
        if schedule.hall.name not in entry["halls"]:
            entry["halls"].append(schedule.hall.name)
        # The prefetch cache holds every item of the menu; filtering it in
        # Python keeps this to one query per week rather than one per row.
        items = [i for i in schedule.menu.items.all() if i.meal == schedule.meal]
        for card in _dish_cards(items):
            if card["name"] in entry["seen"]:
                continue
            entry["seen"].add(card["name"])
            entry["dishes"].append(card)
    for meals in by_date.values():
        for entry in meals.values():
            entry.pop("seen", None)
    return by_date


def _sorted_meals(meals: dict[str, dict]) -> list[dict]:
    return sorted(meals.values(), key=lambda e: MEAL_SERVICE_ORDER.get(e["meal"], 9))


def _student_schedules(start: dt.date, end: dt.date, hall=None):
    schedules = (
        MenuSchedule.objects.filter(
            date__gte=start, date__lte=end, is_published=True
        )
        .select_related("menu", "hall")
        .prefetch_related("menu__items__dish")
        .order_by("date", "meal", "hall__code")
    )
    if hall is not None:
        schedules = schedules.filter(hall=hall)
    return schedules


@login_required
@require_GET
def student_dashboard(request):
    """The student surface: today's menu, own attendance, announcements."""

    if request.user.role != User.Role.STUDENT:
        return JsonResponse({"detail": "Not permitted"}, status=403)

    today = timezone.localdate()
    hall = _selected_hall(request)
    now = timezone.localtime()

    # The whole week is read once, then grouped in Python.
    week_end = today + dt.timedelta(days=6)
    by_date = _menus_by_date(_student_schedules(today, week_end, hall))

    # What is being served today, across halls (a student eats in a hall).
    todays_meals = [
        {**entry, "state": _meal_state(entry["meal"], now)}
        for entry in _sorted_meals(by_date.get(today, {}))
    ]

    # The days ahead, so a student can plan what to come back for.
    week_days = []
    for offset in range(7):
        day = today + dt.timedelta(days=offset)
        week_days.append(
            {
                "date": day,
                "weekday": core_utils.weekday_name(day.isoweekday()),
                "is_today": day == today,
                "meals": [
                    {**entry, "state": "later" if offset else _meal_state(entry["meal"], now)}
                    for entry in _sorted_meals(by_date.get(day, {}))
                ],
            }
        )

    # The student's own attendance only - never another student's.
    identifier = request.user.student_identifier or request.user.username
    attendance_qs = AttendanceRecord.objects.filter(
        student_identifier=identifier
    ).select_related("service", "service__hall")

    recent_attendance = attendance_qs.order_by("-captured_at")[:6]
    attendance_count = attendance_qs.count()
    present_today = attendance_qs.filter(
        service__date=today
    ).values("service").distinct().count()
    last_30_days = attendance_qs.filter(
        service__date__gte=today - dt.timedelta(days=30)
    ).count()
    distinct_halls = attendance_qs.values("service__hall").distinct().count()

    # Four weeks of dots, so the record reads as a rhythm rather than a table.
    window_start = today - dt.timedelta(days=27)
    per_day = (
        attendance_qs.filter(service__date__gte=window_start)
        .values("service__date")
        .annotate(total=models.Count("id"))
        .order_by("service__date")
    )
    counts = {row["service__date"]: row["total"] for row in per_day}
    attendance_dots = [
        {
            "date": window_start + dt.timedelta(days=offset),
            "total": counts.get(window_start + dt.timedelta(days=offset), 0),
            "is_today": window_start + dt.timedelta(days=offset) == today,
        }
        for offset in range(28)
    ]

    # Announcements addressed to this student or to everyone.
    notifications = (
        Notification.objects.filter(
            models.Q(recipient=request.user) | models.Q(role_target=User.Role.STUDENT)
        )
        .order_by("-created_at")[:6]
    )

    hour = now.hour
    greeting = (
        "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
    )

    context = {
        "today": today,
        "hall": hall,
        "halls": DiningHall.objects.filter(is_active=True),
        "greeting": greeting,
        "meals": todays_meals,
        "week_days": week_days,
        "attendance_dots": attendance_dots,
        "recent_attendance": recent_attendance,
        "attendance_count": attendance_count,
        "present_today": present_today,
        "last_30_days": last_30_days,
        "distinct_halls": distinct_halls,
        "notifications": notifications,
    }
    return render(request, "dashboard/student.html", context)


@login_required
@require_GET
def student_menu(request):
    """The week's menu, written out like a printed menu card."""

    if request.user.role != User.Role.STUDENT:
        return JsonResponse({"detail": "Not permitted"}, status=403)

    today = timezone.localdate()
    hall = _selected_hall(request)
    start = today - dt.timedelta(days=today.weekday())
    end = start + dt.timedelta(days=13)

    by_date = _menus_by_date(_student_schedules(start, end, hall))
    days = []
    for offset in range(14):
        day = start + dt.timedelta(days=offset)
        days.append(
            {
                "date": day,
                "weekday": core_utils.weekday_name(day.isoweekday()),
                "is_today": day == today,
                "is_past": day < today,
                "meals": _sorted_meals(by_date.get(day, {})),
            }
        )

    return render(
        request,
        "dashboard/student_menu.html",
        {"today": today, "hall": hall, "days": days},
    )



@login_required
@require_GET
def finance_dashboard(request):
    """The finance officer's read-only financial surface."""

    if request.user.role != User.Role.FINANCE_OFFICER:
        return JsonResponse({"detail": "Not permitted"}, status=403)

    start, end = _range_from_request(request)
    hall = _selected_hall(request)
    today = timezone.localdate()

    totals = waste_services.waste_totals(start, end, hall)
    accuracy = reporting.accuracy_summary(start, end, hall)
    plans = PreparationPlan.objects.filter(
        service__date__gte=start, service__date__lte=end
    ).select_related("service", "service__hall")
    cost_rates = (
        CostRate.objects.filter(
            effective_from__lte=today,
        )
        .filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=today))
        .select_related("ingredient", "hall")
        .order_by("ingredient__name", "hall__code")[:25]
    )

    context = {
        "start": start,
        "end": end,
        "hall": hall,
        "halls": DiningHall.objects.filter(is_active=True),
        "waste_totals": totals,
        "waste_by_week": waste_services.waste_by_week(start, end, hall),
        "mape_over_time": reporting.mape_over_time(start, end, hall),
        "plans": plans[:12],
        "cost_rates": cost_rates,
        "figures": [
            {
                "label": "Cost of waste in period",
                "value": f"₹{totals['waste_cost']:,.0f}",
                "note": f"{totals['waste_quantity_kg']:,.1f} kg across {totals['records']} dish records",
                "tone": "loss",
            },
            {
                "label": "Forecast error (MAPE)",
                "value": f"{accuracy['mape_pct']:,.1f}%",
                "note": f"{accuracy['forecasts']} forecasts scored",
                "tone": "loss" if accuracy["mape_pct"] >= 20 else "match",
            },
            {
                "label": "Plans in window",
                "value": plans.count(),
                "note": "Preparation plans the kitchen is cooking to",
            },
        ],
    }
    return render(request, "dashboard/finance.html", context)

