"""Performance — the acceptance criterion from the specification.

"3,000 attendance records captured in a 45-minute window across halls without
loss."

The test measures the real write path (the same one the offline queue drains
into) rather than a simulation of it.
"""

from __future__ import annotations

import datetime as dt
import time

from django.test import TestCase

from apps.attendance.models import AttendanceRecord
from apps.attendance.services import sync_attendance_batch

from .factories import make_hall, make_service, scan_payload


class ScanThroughputTests(TestCase):
    def test_three_thousand_scans_are_stored_without_loss(self):
        """3,000 scans across two halls inside a 45-minute service window."""
        halls = [make_hall("NORTH", "North"), make_hall("SOUTH", "South")]
        on_date = dt.date(2026, 11, 5)
        services = [make_service(hall, on_date, attendance=0) for hall in halls]

        payloads = []
        for index in range(3000):
            service = services[index % len(services)]
            payloads.append(
                scan_payload(service, f"2023CS{index:06d}", method="QR", offline=False)
            )

        started = time.monotonic()
        result = sync_attendance_batch(payloads, device_id="tablet-load-test")
        elapsed = time.monotonic() - started

        self.assertEqual(result["created"], 3000)
        self.assertEqual(result["duplicates"], 0)
        self.assertEqual(AttendanceRecord.objects.count(), 3000)

        for service in services:
            service.refresh_from_db()
            self.assertEqual(service.attendance_count, 1500)

        # A 45-minute window means roughly one scan per second per hall. The
        # write path has to be comfortably faster than that.
        self.assertLess(elapsed, 45.0, "the sync batch took longer than the service window")

    def test_a_replayed_batch_of_three_thousand_adds_nothing(self):
        """The whole point of the client UUID: a full re-send is harmless."""
        hall = make_hall()
        service = make_service(hall, dt.date(2026, 11, 5), attendance=0)
        payloads = [scan_payload(service, f"2023CS{index:06d}") for index in range(3000)]

        sync_attendance_batch(payloads, device_id="tablet-1")
        replay = sync_attendance_batch(payloads, device_id="tablet-1")

        self.assertEqual(replay["created"], 0)
        self.assertEqual(replay["duplicates"], 3000)
        self.assertEqual(AttendanceRecord.objects.count(), 3000)
