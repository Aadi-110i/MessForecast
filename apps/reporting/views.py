"""HTML surfaces: the admin dashboard and the tablet kitchen screen."""

from __future__ import annotations

import datetime as dt

from django.contrib.auth.decorators import login_required
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
from apps.core.decorators import requires
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

    context = {
        "start": start,
        "end": end,
        "hall": hall,
        "halls": DiningHall.objects.filter(is_active=True),
        "accuracy": accuracy,
        "savings": savings,
        "waste_totals": waste_totals,
        "waste_by_week": waste_services.waste_by_week(start, end, hall),
        "top_dishes": waste_services.top_waste_dishes(start, end, hall, limit=10),
        "mape_over_time": reporting.mape_over_time(start, end, hall),
        "todays_services": todays_services,
        "weekday_pattern": demand_services.attendance_by_weekday(start, end, hall),
        "period": demand_services.attendance_by_period(start, end, hall),
        "demand_summary": demand_summary,
        "figures": [
            {
                "label": "Waste cost in period",
                "value": f"₹{waste_totals['waste_cost']:,.0f}",
                "note": f"{waste_totals['waste_quantity_kg']:,.1f} kg across {waste_totals['records']} dish-services",
                "tone": "loss",
            },
            {
                "label": "Forecast error",
                "value": f"{accuracy['mape_pct']:,.1f}%",
                "note": f"{accuracy['forecasts']} forecasts, {accuracy['within_range']} inside the published range",
                "tone": "loss" if accuracy["mape_pct"] >= 20 else "match",
            },
            {
                "label": "Average turnout",
                "value": f"{demand_summary['avg_attendance']:,.0f}",
                "note": f"{demand_summary['attendance_rate_pct']:,.1f}% of registered strength over {demand_summary['services']} services",
            },
            {
                "label": "Exam-period lift",
                "value": f"{period['exam_lift_pct']:,.1f}%",
                "note": f"{period['exam_avg']:,.0f} students during exams, {period['normal_avg']:,.0f} on ordinary days",
            },
        ],
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

@login_required
@require_GET
def student_dashboard(request):
    """The student surface: today's menu, own attendance, announcements."""

    if request.user.role != User.Role.STUDENT:
        return JsonResponse({"detail": "Not permitted"}, status=403)

    today = timezone.localdate()
    hall = _selected_hall(request)

    # What is being served today, across halls (a student eats in a hall).
    todays_schedules = (
        MenuSchedule.objects.filter(date=today, is_published=True)
        .select_related("menu", "hall")
        .prefetch_related("menu__items__dish")
        .order_by("hall__code", "meal")
    )
    if hall is not None:
        todays_schedules = todays_schedules.filter(hall=hall)

    # Precompute the dishes per meal so the template never calls a method with
    # an argument (Django templates cannot do that).
    for schedule in todays_schedules:
        schedule.dish_names = [
            item.dish.name for item in schedule.menu.items_for_meal(schedule.meal)
        ]

    # Coming meals, so a student can plan ahead.
    end = today + dt.timedelta(days=7)
    upcoming = (
        MenuSchedule.objects.filter(date__gt=today, date__lte=end, is_published=True)
        .select_related("menu", "hall")
        .prefetch_related("menu__items__dish")
        .order_by("date", "meal", "hall__code")[:24]
    )
    for schedule in upcoming:
        schedule.dish_names = [
            item.dish.name for item in schedule.menu.items_for_meal(schedule.meal)
        ]

    # The student's own attendance only - never another student's.
    identifier = request.user.student_identifier or request.user.username
    attendance_qs = AttendanceRecord.objects.filter(
        student_identifier=identifier
    ).select_related("service", "service__hall")

    recent_attendance = attendance_qs.order_by("-captured_at")[:12]
    attendance_count = attendance_qs.count()
    present_today = attendance_qs.filter(
        service__date=today
    ).values("service").distinct().count()
    last_30_days = attendance_qs.filter(
        service__date__gte=today - dt.timedelta(days=30)
    ).count()
    distinct_halls = attendance_qs.values("service__hall").distinct().count()

    # Announcements addressed to this student or to everyone.
    notifications = (
        Notification.objects.filter(
            models.Q(recipient=request.user) | models.Q(role_target=User.Role.STUDENT)
        )
        .order_by("-created_at")[:10]
    )

    context = {
        "today": today,
        "hall": hall,
        "halls": DiningHall.objects.filter(is_active=True),
        "todays_schedules": todays_schedules,
        "upcoming": upcoming,
        "recent_attendance": recent_attendance,
        "attendance_count": attendance_count,
        "present_today": present_today,
        "notifications": notifications,
        "figures": [
            {
                "label": "Meals attended",
                "value": attendance_count,
                "note": "Total recorded swipes",
            },
            {
                "label": "Attended today",
                "value": present_today,
                "note": today.strftime("%d %b %Y"),
            },
            {
                "label": "Last 30 days",
                "value": last_30_days,
                "note": "Meals in the past month",
            },
            {
                "label": "Halls visited",
                "value": distinct_halls,
                "note": "Distinct dining halls",
            },
        ],
    }
    return render(request, "dashboard/student.html", context)


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

