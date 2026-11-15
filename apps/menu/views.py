"""Menu management screens.

The mess manager's side of the menu: which cycles exist, what is in them,
and what is actually scheduled for the week. Everything here is a view
shape — parse, validate, authorise, delegate, format. The rules live in
``apps.menu.services``.
"""

from __future__ import annotations

import datetime as dt
from urllib.parse import quote

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.permissions import has_capability
from apps.catalog.models import DiningHall
from apps.core.console import active_halls, date_window, selected_hall, week_start
from apps.core.constants import MealType
from apps.core.utils import weekday_name
from apps.menu import services as menu_services
from apps.menu.models import Menu, MenuSchedule


def _forbidden():
    return JsonResponse({"detail": "Not permitted"}, status=403)


def _back(message: str, tone: str = "error"):
    """Return to the menu console carrying a message.

    The forms on this screen are plain posts, so they cannot read a JSON
    reply. The message travels in the query string and is shown as a notice.
    """
    return redirect(f"{reverse('console-menus')}?{tone}={quote(message)}")


@login_required
@require_GET
def menu_console(request):
    """The menu console: cycles on the left, the week board on the right."""
    if not has_capability(request.user, "VIEW_MENU"):
        return _forbidden()

    start, end = date_window(request, default_days=28)
    hall = selected_hall(request)
    today = dt.date.today()
    board_start = week_start(today)

    cycles = menu_services.menu_cycles()
    summaries = [menu_services.cycle_summary(m) for m in cycles]

    selected = summaries[0] if summaries else None
    selected_specs = []
    if selected is not None:
        selected_specs = [
            {"name": meal["label"], "value": meal["count"], "note": ", ".join(meal["dishes"][:3])}
            for meal in selected["by_meal"].values()
            if meal["count"]
        ]

    context = {
        "start": start,
        "end": end,
        "today": today,
        "board_start": board_start,
        "hall": hall,
        "halls": active_halls(),
        "cycles": summaries,
        "cycle_options": [{"id": s["menu"].id, "name": s["menu"].name} for s in summaries],
        "board": menu_services.schedule_board(board_start, hall),
        "selected_cycle": selected,
        "selected_cycle_specs": selected_specs,
        "unassigned_dishes": menu_services.unassigned_dishes(),
        "meal_choices": MealType.choices,
        "weekday_names": weekday_name,
        "notice": request.GET.get("notice", ""),
        "form_error": request.GET.get("error", ""),
    }
    return render(request, "console/menus.html", context)


@login_required
@require_GET
def menu_cycle_detail(request, menu_id: int):
    """One cycle: its dishes per meal, and where it is scheduled."""
    if not has_capability(request.user, "VIEW_MENU"):
        return _forbidden()

    menu = get_object_or_404(Menu, pk=menu_id)
    summary = menu_services.cycle_summary(menu)
    schedules = (
        MenuSchedule.objects.filter(menu=menu)
        .select_related("hall")
        .order_by("-date", "meal")[:60]
    )

    context = {
        "summary": summary,
        "grouped": menu_services.cycle_items(menu),
        "schedules": schedules,
        "halls": active_halls(),
        "meal_choices": MealType.choices,
        "unassigned_dishes": menu_services.unassigned_dishes(),
        "cycle_specs": [
            {"name": "Cycle", "value": summary["menu"].code},
            {"name": "Dishes", "value": summary["total_dishes"]},
            {"name": "Scheduled rows", "value": summary["scheduled"]},
            {"name": "Published rows", "value": summary["published"]},
        ],
    }
    return render(request, "console/menu_detail.html", context)


@login_required
@require_POST
def menu_cycle_create(request):
    """Create a new cycle."""
    if not has_capability(request.user, "PLAN_MENU"):
        return _forbidden()

    name = (request.POST.get("name") or "").strip()
    code = (request.POST.get("code") or "").strip()
    cycle_label = (request.POST.get("cycle_label") or "").strip()
    description = (request.POST.get("description") or "").strip()

    if not name or not code:
        return JsonResponse(
            {"detail": "A cycle needs a name and a code"}, status=400
        )
    if Menu.objects.filter(code__iexact=code).exists():
        return JsonResponse({"detail": "That code is already in use"}, status=400)

    menu = menu_services.create_cycle(name, code, cycle_label, description)
    return JsonResponse({"ok": True, "id": menu.id, "url": f"/console/menus/{menu.id}/"})


@login_required
@require_POST
def menu_cycle_items(request, menu_id: int):
    """Replace the dishes for one meal of a cycle."""
    if not has_capability(request.user, "PLAN_MENU"):
        return _forbidden()

    menu = get_object_or_404(Menu, pk=menu_id)
    meal = request.POST.get("meal")
    if meal not in {m.value for m in MealType}:
        return JsonResponse({"detail": "Unknown meal"}, status=400)

    dish_ids = [int(d) for d in request.POST.getlist("dish_ids") if d.isdigit()]
    written = menu_services.set_cycle_items(menu, meal, dish_ids)
    return JsonResponse({"ok": True, "written": written})


@login_required
@require_POST
def menu_schedule_publish(request, schedule_id: int):
    """Publish or unpublish one schedule row."""
    if not has_capability(request.user, "PUBLISH_MENU"):
        return _forbidden()

    published = request.POST.get("published") == "1"
    row = menu_services.publish_schedule(schedule_id, published)
    return JsonResponse({"ok": True, "published": row.is_published})


@login_required
@require_POST
def menu_schedule_assign(request):
    """Point a hall-meal-date at a cycle.

    A slot that already holds a cycle is replaced rather than duplicated.
    The slot is unique on (hall, date, meal), so the row is found by those
    three fields and the cycle on it is changed.
    """
    if not has_capability(request.user, "PLAN_MENU"):
        return _forbidden()

    menu_id = request.POST.get("menu")
    hall_id = request.POST.get("hall")
    date_raw = request.POST.get("date")
    meal = request.POST.get("meal")

    if not all([menu_id, hall_id, date_raw, meal]):
        return _back("A cycle, a hall, a date and a meal are all needed.")

    try:
        on_date = dt.date.fromisoformat(date_raw)
    except ValueError:
        return _back("That date could not be read.")

    if meal not in {m.value for m in MealType}:
        return _back("That is not a meal this kitchen serves.")

    menu = get_object_or_404(Menu, pk=menu_id)
    hall = get_object_or_404(DiningHall, pk=hall_id)
    menu_services.assign_slot(hall, on_date, meal, menu)
    return _back(
        f"{menu.name} now serves {hall.name} on {on_date.strftime('%d %b')} for {meal.title()}.",
        tone="notice",
    )


@login_required
@require_POST
def menu_schedule_day(request):
    """A daily menu: one cycle for every meal of one hall on one date."""
    if not has_capability(request.user, "PLAN_MENU"):
        return _forbidden()

    menu_id = request.POST.get("menu")
    hall_id = request.POST.get("hall")
    date_raw = request.POST.get("date")

    if not all([menu_id, hall_id, date_raw]):
        return _back("A cycle, a hall and a date are all needed.")

    try:
        on_date = dt.date.fromisoformat(date_raw)
    except ValueError:
        return _back("That date could not be read.")

    menu = get_object_or_404(Menu, pk=menu_id)
    hall = get_object_or_404(DiningHall, pk=hall_id)
    written = menu_services.assign_day(hall, on_date, menu)
    return _back(
        f"{written} meals of {menu.name} written for {hall.name} on {on_date.strftime('%d %b')}.",
        tone="notice",
    )


@login_required
@require_POST
def menu_schedule_week(request):
    """A weekly menu: a rotation of cycles across the days of one week."""
    if not has_capability(request.user, "PLAN_MENU"):
        return _forbidden()

    hall_id = request.POST.get("hall")
    start_raw = request.POST.get("start")
    cycle_ids = request.POST.getlist("cycles")

    if not hall_id or not start_raw or not cycle_ids:
        return _back("A hall, the week it starts on and at least one cycle are all needed.")

    try:
        start = dt.date.fromisoformat(start_raw)
    except ValueError:
        return _back("That date could not be read.")

    # The rotation follows the order the cycles are listed in, which is the
    # order the mess itself thinks in: A, B, C and round again.
    cycles = list(Menu.objects.filter(pk__in=cycle_ids).order_by("code"))
    if not cycles:
        return _back("None of those cycles could be found.")

    hall = get_object_or_404(DiningHall, pk=hall_id)
    first = week_start(start)
    written = menu_services.assign_week(hall, first, cycles)
    return _back(
        f"{written} meals written for {hall.name}, the week of {first.strftime('%d %b')}, "
        f"rotating {' then '.join(m.name for m in cycles)}.",
        tone="notice",
    )
