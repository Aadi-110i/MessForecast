"""Measure the real 3,000-scan sync against the live database.

This is the acceptance criterion from the specification:

    "3,000 attendance records captured in a 45-minute window across halls without
    loss."

It drives the same ``sync_attendance_batch`` the offline queue drains into, on
the same PostgreSQL the application uses, inside a transaction that is rolled
back so the database is left untouched.

    python scripts/bench_sync.py
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import time
import uuid as uuid_lib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.db import transaction  # noqa: E402

from apps.attendance.models import AttendanceRecord, MealService  # noqa: E402
from apps.attendance.services import sync_attendance_batch  # noqa: E402
from apps.catalog.models import DiningHall  # noqa: E402


def main() -> int:
    halls = list(DiningHall.objects.order_by("pk")[:2])
    if len(halls) < 2:
        print("This benchmark needs the two seeded dining halls.")
        return 1

    # A date outside the seeded history, so the benchmark owns the services and
    # the unique (hall, date, meal) constraint cannot collide with the seed.
    on_date = dt.date(2026, 12, 15)
    with transaction.atomic():
        services = [
            MealService.objects.create(
                hall=hall,
                date=on_date,
                meal="LUNCH",
                registered_strength=hall.registered_strength,
                attendance_count=0,
            )
            for hall in halls
        ]

        payloads = []
        for index in range(3000):
            service = services[index % len(services)]
            payloads.append(
                {
                    "client_uuid": str(uuid_lib.uuid4()),
                    "service_id": service.id,
                    "hall_id": service.hall_id,
                    "date": on_date.isoformat(),
                    "meal": "LUNCH",
                    "student_identifier": f"2023CS{index:06d}",
                    "method": "QR",
                    "captured_at": dt.datetime.now().isoformat(),
                    "device_id": "tablet-load-test",
                    "captured_offline": False,
                }
            )

        started = time.monotonic()
        result = sync_attendance_batch(payloads, device_id="tablet-load-test")
        elapsed = time.monotonic() - started

        stored = AttendanceRecord.objects.filter(
            service__in=services
        ).count()

        print(f"3,000 scans sent in a single batch")
        print(f"  created      : {result['created']}")
        print(f"  duplicates   : {result['duplicates']}")
        print(f"  stored       : {stored}")
        print(f"  elapsed      : {elapsed:.3f} s")
        print(f"  throughput   : {3000 / elapsed:,.0f} scans/second")
        print(f"  per scan     : {elapsed / 3000 * 1000:.3f} ms")
        print()
        print(f"  a 45-minute window at one scan per second needs 2,700 scans")
        print(f"  headroom     : {2700 / (3000 / elapsed):,.0f}x")

        # Now the replay: the same batch again must change nothing.
        started = time.monotonic()
        replay = sync_attendance_batch(payloads, device_id="tablet-load-test")
        replay_elapsed = time.monotonic() - started
        after = AttendanceRecord.objects.filter(service__in=services).count()

        print()
        print(f"replay of the same 3,000 scans")
        print(f"  created      : {replay['created']}")
        print(f"  duplicates   : {replay['duplicates']}")
        print(f"  stored       : {after}")
        print(f"  elapsed      : {replay_elapsed:.3f} s")

        raise transaction.TransactionManagementError("rolled back")  # noqa: TRY301


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        if "rolled back" in str(exc):
            print("\n(rolled back - the database is unchanged)")
            sys.exit(0)
        raise
