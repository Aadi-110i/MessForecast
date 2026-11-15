"""Attendance capture screen and its endpoints.

The capture screen is the surface where 3,000 scans have to land inside a
45-minute window. It works the same way online and offline: the JavaScript
queues every scan into IndexedDB with a client-generated UUID, then drains the
queue into ``/api/attendance/sync`` whenever there is a connection.
"""

from __future__ import annotations

import datetime as dt

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.attendance.models import MealService
from apps.attendance.services import sync_attendance_batch
from apps.catalog.models import DiningHall
from apps.core.decorators import requires


@login_required
@requires("RECORD_ATTENDANCE")
@require_GET
def scan_screen(request):
    """The attendance capture screen."""
    today = timezone.localdate()
    services = MealService.objects.filter(date=today).select_related("hall")
    if request.user.role == "KITCHEN_STAFF" and request.user.hall_id:
        services = services.filter(hall_id=request.user.hall_id)

    context = {
        "today": today,
        "services": services,
        "halls": DiningHall.objects.filter(is_active=True),
    }
    return render(request, "scan/index.html", context)


@login_required
@requires("RECORD_ATTENDANCE")
@require_GET
def scan_services(request):
    """Services available for scanning today, as JSON."""
    today = timezone.localdate()
    services = MealService.objects.filter(date=today).select_related("hall")
    if request.user.role == "KITCHEN_STAFF" and request.user.hall_id:
        services = services.filter(hall_id=request.user.hall_id)
    return JsonResponse(
        {
            "services": [
                {
                    "id": s.id,
                    "hall_id": s.hall_id,
                    "hall": s.hall.name,
                    "date": s.date.isoformat(),
                    "meal": s.meal,
                    "meal_display": s.get_meal_display(),
                    "attendance_count": s.attendance_count,
                    "registered_strength": s.registered_strength,
                }
                for s in services
            ]
        }
    )


@login_required
@requires("RECORD_ATTENDANCE")
@require_POST
def capture_scan(request):
    """Record a single scan.

    The screen prefers to batch, but a single-scan endpoint is useful when the
    tablet has a connection and the operator is scanning one student at a time.

    Recording attendance is the kitchen's job, so this needs the same
    capability as the batch endpoint it mirrors.
    """
    import json

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON body"}, status=400)

    payload.setdefault("device_id", request.headers.get("X-Device-Id", ""))
    payload.setdefault("client_uuid", str(__import__("uuid").uuid4()))
    payload.setdefault("student_identifier", "")
    payload.setdefault("captured_offline", False)

    result = sync_attendance_batch([payload], device_id=payload.get("device_id", ""))
    return JsonResponse(result)


@login_required
@requires("RECORD_ATTENDANCE")
@require_GET
def scan_count(request):
    """Live count for the currently open service."""
    # This is a plain Django view, not a DRF view, so the query string is on
    # request.GET - request.query_params only exists on DRF requests.
    service_id = request.GET.get("service")
    if not service_id:
        return JsonResponse({"detail": "service is required"}, status=400)
    service = get_object_or_404(MealService.objects.select_related("hall"), pk=service_id)
    return JsonResponse(
        {
            "service": service.id,
            "attendance_count": service.attendance_count,
            "registered_strength": service.registered_strength,
            "updated_at": timezone.now().isoformat(),
        }
    )


def _resolve_qr_service(qr_text: str) -> MealService | None:
    """Resolve a scanned QR payload into a MealService."""
    import json

    text = (qr_text or "").strip()
    if not text:
        return None

    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if data.get("service_id"):
            return MealService.objects.select_related("hall").filter(pk=data["service_id"]).first()
        hall_id = data.get("hall_id")
        meal = (data.get("meal") or "").upper()
        date_str = data.get("date") or timezone.localdate().isoformat()
        if hall_id and meal:
            return (
                MealService.objects.select_related("hall")
                .filter(hall_id=hall_id, date=date_str, meal=meal)
                .first()
            )
        return None

    upper = text.upper()
    if upper.startswith("MESSFORECAST:SERVICE:"):
        text = text.split(":", 2)[2].strip()
    elif upper.startswith("SERVICE:"):
        text = text.split(":", 1)[1].strip()
    elif upper.startswith("MESSFORECAST:HALL:"):
        parts = text.split(":")
        if len(parts) >= 4:
            hall_id, meal = parts[2].strip(), parts[3].strip().upper()
            if hall_id.isdigit():
                return (
                    MealService.objects.select_related("hall")
                    .filter(hall_id=int(hall_id), date=timezone.localdate(), meal=meal)
                    .first()
                )
        return None

    if text.isdigit():
        return MealService.objects.select_related("hall").filter(pk=int(text)).first()
    return None


@login_required
@requires("VIEW_OWN_ATTENDANCE")
@require_POST
def student_qr_checkin(request):
    """Allow an authenticated student to mark their own attendance by scanning a meal QR code."""
    import json
    import uuid

    from apps.attendance.models import AttendanceRecord

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON body"}, status=400)

    qr_text = payload.get("qr_text") or (
        str(payload["service_id"]) if payload.get("service_id") else ""
    )
    service = _resolve_qr_service(qr_text)
    if service is None:
        return JsonResponse(
            {"detail": "QR code did not match an active meal service."},
            status=400,
        )

    identifier = request.user.student_identifier or request.user.username
    if AttendanceRecord.objects.filter(service=service, student_identifier=identifier).exists():
        return JsonResponse(
            {
                "ok": True,
                "already_marked": True,
                "service_id": service.id,
                "meal": service.get_meal_display(),
                "hall": service.hall.name,
                "date": service.date.isoformat(),
                "detail": f"Attendance already marked for {service.get_meal_display()} at {service.hall.name}.",
            }
        )

    sync_attendance_batch(
        [
            {
                "client_uuid": str(uuid.uuid4()),
                "service_id": service.id,
                "hall_id": service.hall_id,
                "date": service.date.isoformat(),
                "meal": service.meal,
                "student_identifier": identifier,
                "method": "QR",
                "captured_at": timezone.now().isoformat(),
                "captured_offline": False,
            }
        ],
        device_id="student-qr",
    )
    return JsonResponse(
        {
            "ok": True,
            "already_marked": False,
            "service_id": service.id,
            "meal": service.get_meal_display(),
            "hall": service.hall.name,
            "date": service.date.isoformat(),
            "detail": f"Attendance marked for {service.get_meal_display()} at {service.hall.name}.",
        }
    )
