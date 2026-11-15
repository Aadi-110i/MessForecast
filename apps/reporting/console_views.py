"""HTML surfaces for the administrative console.

The console is the mess manager's and administrator's side of the platform.
It is information-dense: tables before cards, charts beside the numbers they
explain, and every figure computed from recorded services rather than typed
in by hand.

The screens are split across the apps that own the data they show, so a
domain rule lives in one place. This module holds only the cross-cutting
surfaces that span domains: the reports catalogue and the settings screens.
"""

from __future__ import annotations

import datetime as dt
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.permissions import has_capability
from apps.accounts.models import User
from apps.actuals.models import ServiceActual
from apps.attendance.models import AttendanceAudit, MealService
from apps.catalog.models import DiningHall
from apps.core.constants import EventType, MealType
from apps.core.utils import csv_response
from apps.events import services as event_services
from apps.events.models import CalendarEvent, ServiceLevelConfig
from apps.forecasting.models import Forecast
from apps.menu.models import Menu, MenuSchedule
from apps.planning.models import PreparationPlan
from apps.reporting import services as reporting
from apps.waste import services as waste_services
from apps.waste.models import WasteRecord


@login_required
@require_GET
def reports_catalogue(request):
    """The catalogue of reports the platform can produce.

    Each row is a real dataset with a real export behind it, so a manager
    can see what is available without guessing at the URL.
    """
    if not (
        has_capability(request.user, "VIEW_WASTE_COST")
        or has_capability(request.user, "VIEW_ACCURACY")
        or has_capability(request.user, "MANAGE_MASTERS")
    ):
        return JsonResponse({"detail": "Not permitted"}, status=403)

    today = timezone.localdate()
    start = today - dt.timedelta(days=28)
    end = today

    context = {
        "today": today,
        "start": start,
        "end": end,
        "figures": [
            {
                "label": "Services in window",
                "value": MealService.objects.filter(date__gte=start, date__lte=end).count(),
                "note": "Every service scheduled in the last 28 days",
            },
            {
                "label": "Actuals recorded",
                "value": ServiceActual.objects.filter(service__date__gte=start, service__date__lte=end).count(),
                "note": "Prepared, served and leftover, per service",
            },
            {
                "label": "Forecasts to score",
                "value": Forecast.objects.filter(service__date__gte=start, service__date__lte=end).count(),
                "note": "Each one can be compared with what turned up",
            },
            {
                "label": "Schedule rows",
                "value": MenuSchedule.objects.filter(date__gte=start, date__lte=end).count(),
                "note": f"{MenuSchedule.objects.filter(date__gte=start, date__lte=end, is_published=True).count()} published",
            },
        ],
        "reports": [
            {
                "name": "Service ledger",
                "answers": "Every service with its forecast, its plan and what was actually served",
                "rows": MealService.objects.filter(date__gte=start, date__lte=end).count(),
                "format": "CSV",
                "url": "/console/export/service-ledger.csv",
                "capability": "VIEW_WASTE_COST",
            },
            {
                "name": "Attendance sync log",
                "answers": "What each tablet sent, what was created, and what was rejected",
                "rows": AttendanceAudit.objects.filter(batch_started_at__date__gte=start).count(),
                "format": "CSV",
                "url": "/console/export/attendance.csv",
                "capability": "RECORD_ATTENDANCE",
            },
            {
                "name": "Ingredient indent",
                "answers": "What to buy for one preparation plan, in the procurement format",
                "rows": PreparationPlan.objects.filter(service__date__gte=start, service__date__lte=end).count(),
                "format": "CSV",
                "url": "/dashboard/planning/",
                "capability": "VIEW_PREPARATION_PLAN",
            },
            {
                "name": "Waste by dish",
                "answers": "What was thrown away, how much of it, and what it cost",
                "rows": WasteRecord.objects.filter(service_date__gte=start, service_date__lte=end).count(),
                "format": "On screen",
                "url": "/dashboard/waste/",
                "capability": "VIEW_WASTE_COST",
            },
            {
                "name": "Forecast accuracy",
                "answers": "How close the forecast landed, by meal and by hall",
                "rows": Forecast.objects.filter(service__date__gte=start, service__date__lte=end).count(),
                "format": "On screen",
                "url": "/dashboard/accuracy/",
                "capability": "VIEW_ACCURACY",
            },
        ],
        "window_specs": [
            {"name": "Window", "value": f"{start.strftime('%d %b')} to {end.strftime('%d %b %Y')}"},
            {"name": "Menu cycles", "value": Menu.objects.filter(is_active=True).count()},
            {"name": "Waste records", "value": WasteRecord.objects.filter(service_date__gte=start, service_date__lte=end).count()},
            {"name": "Sync batches", "value": AttendanceAudit.objects.filter(batch_started_at__date__gte=start).count()},
        ],
    }
    return render(request, "console/reports.html", context)


@login_required
@require_GET
def settings_overview(request):
    """The settings screen: halls, service levels, people and the calendar."""
    if not (
        has_capability(request.user, "MANAGE_HALLS")
        or has_capability(request.user, "MANAGE_MASTERS")
        or has_capability(request.user, "CONFIGURE_SERVICE_LEVEL")
    ):
        return JsonResponse({"detail": "Not permitted"}, status=403)

    today = timezone.localdate()
    window_start = today - dt.timedelta(days=28)

    # The event form. An event being corrected is loaded into the same form
    # rather than onto a second screen.
    editing_event = None
    event_id = request.GET.get("event")
    if event_id and event_id.isdigit():
        editing_event = CalendarEvent.objects.filter(pk=int(event_id)).first()

    if editing_event is not None:
        event_values = {
            "name": editing_event.name,
            "start_date": editing_event.start_date.isoformat(),
            "end_date": editing_event.end_date.isoformat(),
            "impact_factor": f"{editing_event.impact_factor:f}",
        }
        event_action = reverse("console-event-update", args=[editing_event.pk])
        event_heading = f"Edit {editing_event.name}"
        event_button = "Save the event"
    else:
        event_values = {
            "name": "",
            "start_date": today.isoformat(),
            "end_date": today.isoformat(),
            "impact_factor": "1.00",
        }
        event_action = reverse("console-event-create")
        event_heading = "Add an event"
        event_button = "Add the event"

    context = {
        "today": today,
        "start": window_start,
        "halls": DiningHall.objects.all().order_by("name"),
        "level_configs": ServiceLevelConfig.objects.select_related("hall").order_by(
            "-effective_from", "hall__code", "meal"
        ),
        "events": CalendarEvent.objects.filter(is_active=True).order_by("-start_date")[:20],
        "people": User.objects.select_related("hall").order_by("role", "username"),
        "roles": User.Role.choices,
        "capability_rows": _capability_matrix(),
        "waste_totals": waste_services.waste_totals(window_start, today, None),
        "accuracy": reporting.accuracy_summary(window_start, today, None),
        "event_type_choices": EventType.choices,
        "meal_choices": MealType.choices,
        "event_values": event_values,
        "event_errors": {},
        "event_action": event_action,
        "event_heading": event_heading,
        "event_button": event_button,
        "editing_event": editing_event,
        "notice": request.GET.get("notice", ""),
        "form_error": request.GET.get("error", ""),
        "window_specs": [
            {"name": "Window", "value": f"{window_start.strftime('%d %b')} to {today.strftime('%d %b %Y')}"},
            {"name": "Waste cost", "value": f"₹{waste_services.waste_totals(window_start, today, None).get('waste_cost', 0):,.0f}", "tone": "loss"},
            {"name": "Forecast error", "value": f"{reporting.accuracy_summary(window_start, today, None).get('mape_pct', 0)}%"},
            {"name": "Halls", "value": DiningHall.objects.count()},
        ],
    }
    return render(request, "console/settings.html", context)


def _capability_matrix() -> list[dict]:
    """The role to capability table, read from the one place that defines it."""
    from apps.accounts.permissions import CAPABILITIES

    all_caps = sorted({cap for caps in CAPABILITIES.values() for cap in caps})
    rows = []
    for role, label in User.Role.choices:
        held = CAPABILITIES.get(role, set())
        rows.append(
            {
                "role": label,
                "caps": [{"name": cap, "held": cap in held} for cap in all_caps],
            }
        )
    return rows


# ---------------------------------------------------------------------------
# The calendar
# ---------------------------------------------------------------------------


def _event_fields(request):
    """Read and validate the event form."""
    from decimal import Decimal, InvalidOperation

    from apps.events import services as event_services

    name = (request.POST.get("name") or "").strip()
    event_type = request.POST.get("event_type") or "OTHER"
    start_raw = (request.POST.get("start_date") or "").strip()
    end_raw = (request.POST.get("end_date") or "").strip()
    factor_raw = (request.POST.get("impact_factor") or "1.000").strip()
    meals_raw = request.POST.get("affects_meals") or ""
    description = (request.POST.get("description") or "").strip()
    hall_ids = request.POST.getlist("affects_halls")

    errors = {}

    if not name:
        errors["name"] = "An event needs a name."
    if event_type not in {t.value for t in EventType}:
        errors["event_type"] = "That kind of event is not one the calendar knows."

    try:
        start = dt.date.fromisoformat(start_raw)
    except ValueError:
        errors["start_date"] = "The first day could not be read."
        start = None
    try:
        end = dt.date.fromisoformat(end_raw)
    except ValueError:
        errors["end_date"] = "The last day could not be read."
        end = None
    if start and end and end < start:
        errors["end_date"] = "An event cannot finish before it starts."

    try:
        factor = Decimal(factor_raw)
        if factor < 0:
            errors["impact_factor"] = "The effect cannot be negative."
        elif factor > 5:
            errors["impact_factor"] = "An effect above five is a typo, not a forecast."
    except (InvalidOperation, TypeError, ValueError):
        errors["impact_factor"] = "The effect could not be read."
        factor = None

    return {
        "name": name,
        "event_type": event_type,
        "start_date": start,
        "end_date": end,
        "impact_factor": factor,
        "affects_meals": event_services.parse_meals(meals_raw),
        "affects_halls": list(DiningHall.objects.filter(pk__in=hall_ids)) if hall_ids else [],
        "description": description,
        "errors": errors,
    }


def _event_back(errors=None, notice: str = "", event=None):
    """Return to the settings screen carrying a message.

    The event form is a plain post, so it cannot read a JSON reply. The
    message travels in the query string and is shown as a notice. When the
    form did not save, the event being edited goes back with it, so the
    reader does not lose what they typed.
    """
    query = {}
    if notice:
        query["notice"] = notice
    if errors:
        first = next(iter(errors.values()), "")
        query["error"] = first if isinstance(first, str) else ", ".join(first)
    if event is not None:
        query["event"] = event.pk
    url = reverse("console-settings")
    if query:
        url = f"{url}?{urlencode(query)}"
    return redirect(url)


@login_required
def event_create(request):
    """Put an event on the calendar."""
    if not has_capability(request.user, "PLAN_MENU"):
        return JsonResponse({"detail": "Not permitted"}, status=403)

    if request.method == "GET":
        return redirect("console-settings")

    fields = _event_fields(request)
    if fields["errors"]:
        return _event_back(fields["errors"])

    event = event_services.create_event(
        name=fields["name"],
        event_type=fields["event_type"],
        start_date=fields["start_date"],
        end_date=fields["end_date"],
        impact_factor=fields["impact_factor"],
        affects_meals=fields["affects_meals"],
        affects_halls=fields["affects_halls"],
        description=fields["description"],
    )
    return _event_back({}, notice=f"{event.name} added to the calendar.")


@login_required
def event_update(request, event_id: int):
    """Correct an event that is already on the calendar."""
    if not has_capability(request.user, "PLAN_MENU"):
        return JsonResponse({"detail": "Not permitted"}, status=403)

    event = get_object_or_404(CalendarEvent, pk=event_id)

    if request.method == "GET":
        return redirect(f"{reverse('console-settings')}?event={event.pk}")

    fields = _event_fields(request)
    if fields["errors"]:
        return _event_back(fields["errors"], event=event)

    event_services.update_event(
        event,
        name=fields["name"],
        event_type=fields["event_type"],
        start_date=fields["start_date"],
        end_date=fields["end_date"],
        impact_factor=fields["impact_factor"],
        affects_meals=fields["affects_meals"],
        affects_halls=fields["affects_halls"],
        description=fields["description"],
    )
    return _event_back({}, notice=f"{event.name} corrected.", event=event)


@login_required
@require_POST
def event_delete(request, event_id: int):
    """Take an event off the calendar, or delete it outright."""
    if not has_capability(request.user, "PLAN_MENU"):
        return JsonResponse({"detail": "Not permitted"}, status=403)

    event = get_object_or_404(CalendarEvent, pk=event_id)

    if request.POST.get("action") == "retire":
        event_services.retire_event(event)
        return _event_back({}, notice=f"{event.name} taken off the calendar.")

    event_services.delete_event(event)
    return _event_back({}, notice=f"{event.name} deleted.")


@login_required
@require_GET
def export_service_ledger_csv(request):
    """Every service in the window with its forecast, plan and actual."""
    if not has_capability(request.user, "VIEW_WASTE_COST"):
        return JsonResponse({"detail": "Not permitted"}, status=403)

    end = timezone.localdate()
    start = end - dt.timedelta(days=28)
    services = (
        MealService.objects.filter(date__gte=start, date__lte=end)
        .select_related("hall", "forecast", "preparation_plan", "actual")
        .order_by("date", "meal")
    )

    header = [
        "date", "hall", "meal", "registered_strength", "attendance",
        "forecast", "lower_bound", "upper_bound",
        "portions_to_prepare", "prepared", "served", "leftover", "waste_cost",
    ]
    rows = []
    for s in services:
        actual = getattr(s, "actual", None)
        forecast = getattr(s, "forecast", None)
        plan = getattr(s, "preparation_plan", None)
        rows.append([
            s.date.isoformat(),
            s.hall.code,
            s.get_meal_display(),
            s.registered_strength,
            s.attendance_count,
            str(forecast.predicted_attendance) if forecast else "",
            str(forecast.lower_bound) if forecast else "",
            str(forecast.upper_bound) if forecast else "",
            plan.portions_to_prepare if plan else "",
            actual.prepared_portions_total if actual else "",
            actual.served_portions_total if actual else "",
            actual.leftover_portions_total if actual else "",
            "",
        ])

    return csv_response(f"service_ledger_{start.isoformat()}_{end.isoformat()}.csv", header, rows)


@login_required
@require_GET
def export_attendance_csv(request):
    """Attendance capture methods and sync health."""
    if not has_capability(request.user, "RECORD_ATTENDANCE"):
        return JsonResponse({"detail": "Not permitted"}, status=403)

    end = timezone.localdate()
    start = end - dt.timedelta(days=28)

    audits = AttendanceAudit.objects.filter(batch_started_at__date__gte=start).order_by("-batch_started_at")

    header = ["device", "received", "created", "duplicates", "failed", "started_at", "finished_at"]
    rows = [
        [
            a.device_id or "unknown device",
            a.received,
            a.created,
            a.duplicates,
            a.failed,
            a.batch_started_at.isoformat() if a.batch_started_at else "",
            a.batch_finished_at.isoformat() if a.batch_finished_at else "",
        ]
        for a in audits
    ]
    return csv_response(f"attendance_sync_{start.isoformat()}_{end.isoformat()}.csv", header, rows)
