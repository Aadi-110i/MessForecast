"""Attendance capture and offline sync.

``sync_attendance_batch`` is the endpoint the tablet calls when connectivity
returns. It must be:

* **Idempotent** - replaying the same batch stores nothing new.
* **Order independent** - a record may arrive before the service it belongs to.
* **Cheap** - a 45 minute window across halls means thousands of rows in one
  burst, so writes go through ``bulk_create`` rather than a query per scan.
"""

from __future__ import annotations

import datetime as dt
import uuid as uuid_lib

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.attendance.models import AttendanceAudit, AttendanceRecord, MealService
from apps.core.constants import CaptureMethod


class AttendanceError(Exception):
    """Raised when a scan cannot be attached to a service."""


def _resolve_service(payload: dict) -> MealService:
    """Find the MealService a scan belongs to, creating it when justified.

    The tablet sends hall + date + meal (it does not know our surrogate keys).
    A service row is created on demand so that a scan is never lost, but only
    when the hall/date/meal combination is unambiguous.
    """
    service_id = payload.get("service_id")
    if service_id:
        service = MealService.objects.filter(pk=service_id).first()
        if service is None:
            raise AttendanceError(f"Meal service {service_id} does not exist")
        return service

    hall_id = payload.get("hall_id")
    date = payload.get("date")
    meal = payload.get("meal")
    if not (hall_id and date and meal):
        raise AttendanceError("A scan needs either service_id or hall_id + date + meal")

    try:
        date = dt.date.fromisoformat(str(date))
    except ValueError as exc:
        raise AttendanceError(f"Invalid date {date!r}") from exc

    service, _ = MealService.objects.get_or_create(
        hall_id=hall_id,
        date=date,
        meal=meal,
        defaults={
            "registered_strength": payload.get("registered_strength", 0) or 0,
            "prep_mode": payload.get("prep_mode", "REGISTERED_STRENGTH"),
        },
    )
    return service


def _parse_timestamp(value) -> dt.datetime:
    if not value:
        return timezone.now()
    if isinstance(value, dt.datetime):
        return value
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return timezone.now()
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


@transaction.atomic
def sync_attendance_batch(payloads: list[dict], device_id: str = "") -> dict:
    """Store a batch of scans, ignoring any UUID the server already holds.

    Returns a summary with ``created`` and ``duplicates`` counts so the kitchen
    screen can show the operator exactly what happened.
    """
    audit = AttendanceAudit(device_id=device_id or "unknown", received=len(payloads))

    # 1. Collapse duplicate UUIDs inside the batch itself. A tablet that lost
    #    its connection may queue the same scan twice before it ever reaches us.
    by_uuid: dict[uuid_lib.UUID, dict] = {}
    rejected: list[dict] = []
    for payload in payloads:
        raw_uuid = payload.get("client_uuid")
        try:
            key = uuid_lib.UUID(str(raw_uuid))
        except (ValueError, TypeError, AttributeError):
            rejected.append({"client_uuid": str(raw_uuid), "reason": "malformed client_uuid"})
            continue
        by_uuid.setdefault(key, payload)

    if not by_uuid:
        audit.failed = len(rejected)
        audit.detail = {"rejected": rejected[:50]}
        audit.batch_finished_at = timezone.now()
        audit.save()
        return {
            "received": audit.received,
            "created": 0,
            "duplicates": 0,
            "failed": audit.failed,
            "rejected": rejected[:50],
        }

    uuids = list(by_uuid.keys())

    # 2. Which UUIDs do we already hold? This is what makes the operation
    #    idempotent: anything in this set is simply skipped.
    already_stored = set(
        AttendanceRecord.objects.filter(client_uuid__in=uuids).values_list("client_uuid", flat=True)
    )

    # 3. Resolve the service and the student for each accepted scan.
    identifiers = {str(p.get("student_identifier", "")).strip() for p in by_uuid.values()}
    identifiers.discard("")
    students = {}
    if identifiers:
        from apps.accounts.models import User

        for user in User.objects.filter(student_identifier__in=identifiers):
            students[user.student_identifier] = user

    rows: list[AttendanceRecord] = []
    service_ids: set[int] = set()
    for key, payload in by_uuid.items():
        if key in already_stored:
            continue
        try:
            service = _resolve_service(payload)
        except AttendanceError as exc:
            rejected.append({"client_uuid": str(key), "reason": str(exc)})
            continue

        identifier = str(payload.get("student_identifier", "")).strip()
        student = students.get(identifier)
        method = payload.get("method") or CaptureMethod.QR
        if method not in CaptureMethod.values:
            method = CaptureMethod.QR

        rows.append(
            AttendanceRecord(
                client_uuid=key,
                service=service,
                hall=service.hall,
                meal=service.meal,
                student=student,
                student_identifier=identifier,
                method=method,
                captured_at=_parse_timestamp(payload.get("captured_at")),
                device_id=str(payload.get("device_id", device_id))[:64],
                captured_offline=bool(payload.get("captured_offline", False)),
                synced_at=timezone.now(),
            )
        )
        service_ids.add(service.id)

    # 4. One bulk insert. ignore_conflicts=True is the belt-and-braces guard:
    #    even if two devices race on the same UUID, the unique constraint wins
    #    and the second insert is dropped rather than corrupting the count.
    if rows:
        AttendanceRecord.objects.bulk_create(rows, ignore_conflicts=True, batch_size=1000)

    # 5. Exact accounting: which of the submitted UUIDs exist now that did not
    #    exist before?
    present_now = set(
        AttendanceRecord.objects.filter(client_uuid__in=uuids).values_list("client_uuid", flat=True)
    )
    created = len(present_now - already_stored)
    duplicates = len(present_now & already_stored)

    # 6. Keep the denormalised counter in step.
    if service_ids:
        _refresh_attendance_counts(service_ids)

    audit.created = created
    audit.duplicates = duplicates
    audit.failed = len(rejected)
    audit.detail = {"rejected": rejected[:50]}
    audit.batch_finished_at = timezone.now()
    audit.save()

    return {
        "received": audit.received,
        "created": created,
        "duplicates": duplicates,
        "failed": audit.failed,
        "rejected": rejected[:50],
        "audit_id": audit.id,
    }


def _refresh_attendance_counts(service_ids) -> None:
    """Recompute ``attendance_count`` for the given services from the records."""
    counts = (
        AttendanceRecord.objects.filter(service_id__in=service_ids)
        .values("service_id")
        .annotate(total=Count("id"))
    )
    for row in counts:
        MealService.objects.filter(pk=row["service_id"]).update(attendance_count=row["total"])


def rebuild_attendance_counts() -> int:
    """Recompute every service's counter. Used by the seed and by a repair command."""
    service_ids = list(MealService.objects.values_list("id", flat=True))
    _refresh_attendance_counts(service_ids)
    return len(service_ids)


def attendance_summary(services) -> dict:
    """Aggregate attendance for a queryset of services."""
    from django.db.models import Sum

    totals = services.aggregate(total=Sum("attendance_count"), services=Count("id"))
    return {
        "total_attendance": totals["total"] or 0,
        "services": totals["services"] or 0,
    }
