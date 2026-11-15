"""Attendance console.

The manager's view of attendance: what turned up, how it was captured, and
whether the tablets are syncing. The capture screen is a different surface
for a different audience — this one is read, and it is read closely.
"""

from __future__ import annotations

import datetime as dt

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.accounts.permissions import has_capability
from apps.attendance.models import AttendanceAudit, AttendanceRecord, MealService
from apps.core.console import active_halls, date_window, selected_hall


@login_required
@require_GET
def attendance_console(request):
    """Attendance across the window: totals, methods, sync health, per service."""
    if not (
        has_capability(request.user, "RECORD_ATTENDANCE")
        or has_capability(request.user, "VIEW_ACCURACY")
    ):
        return JsonResponse({"detail": "Not permitted"}, status=403)

    start, end = date_window(request, default_days=28)
    hall = selected_hall(request)

    services = MealService.objects.filter(date__gte=start, date__lte=end)
    if hall is not None:
        services = services.filter(hall=hall)

    totals = services.aggregate(
        attendance=Sum("attendance_count"),
        registered=Sum("registered_strength"),
        count=Count("id"),
    )
    registered = totals["registered"] or 0
    attendance = totals["attendance"] or 0

    records = AttendanceRecord.objects.filter(
        service__date__gte=start, service__date__lte=end
    )
    if hall is not None:
        records = records.filter(hall=hall)

    by_method = list(
        records.values("method")
        .annotate(
            count=Count("id"),
            offline=Count("id", filter=Q(captured_offline=True)),
            unsynced=Count("id", filter=Q(synced_at__isnull=True)),
        )
        .order_by("-count")
    )

    audits = list(
        AttendanceAudit.objects.filter(batch_started_at__date__gte=start)
        .order_by("-batch_started_at")[:25]
    )

    service_rows = (
        services.select_related("hall", "forecast")
        .order_by("-date", "meal")[:120]
    )

    context = {
        "start": start,
        "end": end,
        "hall": hall,
        "halls": active_halls(),
        "services": service_rows,
        "totals": {
            "attendance": attendance,
            "registered": registered,
            "services": totals["count"] or 0,
            "rate": round(attendance / registered * 100, 1) if registered else 0.0,
            "records": records.count(),
            "offline": sum(r["offline"] for r in by_method),
            "unsynced": sum(r["unsynced"] for r in by_method),
        },
        "figures": [
            {
                "label": "Turned up",
                "value": f"{attendance:,}",
                "note": f"Across {totals['count'] or 0} services",
            },
            {
                "label": "Of registered strength",
                "value": f"{round(attendance / registered * 100, 1) if registered else 0.0}%",
                "note": f"{registered:,} registered",
            },
            {
                "label": "Scans captured",
                "value": f"{records.count():,}",
                "note": f"{sum(r['offline'] for r in by_method):,} taken offline and queued",
            },
            {
                "label": "Still unsynced",
                "value": f"{sum(r['unsynced'] for r in by_method):,}",
                "note": "Waiting for a tablet to reconnect",
            },
        ],
        "by_method": by_method,
        "method_labels": dict(
            AttendanceRecord._meta.get_field("method").choices
        ),
        "audits": audits,
        "audit_specs": [
            {"name": "Scans received", "value": f"{sum(a.received for a in audits):,}"},
            {"name": "Records created", "value": f"{sum(a.created for a in audits):,}"},
            {"name": "Duplicates ignored", "value": f"{sum(a.duplicates for a in audits):,}"},
            {"name": "Rejected", "value": f"{sum(a.failed for a in audits):,}"},
        ],
    }
    return render(request, "console/attendance.html", context)
