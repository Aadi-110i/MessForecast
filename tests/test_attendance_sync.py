"""M2 — offline attendance capture and sync.

The specification requires this test explicitly:
"offline attendance capture and sync, including a duplicate-submission case".
"""

from __future__ import annotations

import datetime as dt
import uuid as uuid_lib

from django.test import TestCase

from apps.attendance.models import AttendanceAudit, AttendanceRecord
from apps.attendance.services import sync_attendance_batch

from .factories import make_hall, make_service, scan_payload


class OfflineSyncTests(TestCase):
    def setUp(self):
        self.hall = make_hall()
        self.service = make_service(
            self.hall, dt.date(2026, 11, 5), attendance=0
        )

    def test_batch_of_scans_is_stored(self):
        """Scans taken offline arrive and are counted."""
        payloads = [
            scan_payload(self.service, f"2023CS{index:04d}") for index in range(25)
        ]

        result = sync_attendance_batch(payloads, device_id="tablet-01")

        self.assertEqual(result["created"], 25)
        self.assertEqual(result["duplicates"], 0)
        self.assertEqual(AttendanceRecord.objects.count(), 25)

        self.service.refresh_from_db()
        self.assertEqual(self.service.attendance_count, 25)

    def test_resending_the_same_batch_stores_nothing_new(self):
        """The duplicate-submission case: the same batch replayed is a no-op."""
        payloads = [
            scan_payload(self.service, f"2023CS{index:04d}") for index in range(10)
        ]

        first = sync_attendance_batch(payloads, device_id="tablet-01")
        second = sync_attendance_batch(payloads, device_id="tablet-01")

        self.assertEqual(first["created"], 10)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["duplicates"], 10)
        # The attendance count must not have moved.
        self.assertEqual(AttendanceRecord.objects.count(), 10)
        self.service.refresh_from_db()
        self.assertEqual(self.service.attendance_count, 10)

    def test_a_single_duplicated_uuid_inside_one_batch_is_stored_once(self):
        """A tablet that queues the same scan twice before syncing sends one record."""
        shared_uuid = str(uuid_lib.uuid4())
        payloads = [
            scan_payload(self.service, "2023CS0001", client_uuid=shared_uuid),
            scan_payload(self.service, "2023CS0001", client_uuid=shared_uuid),
            scan_payload(self.service, "2023CS0002"),
        ]

        result = sync_attendance_batch(payloads, device_id="tablet-01")

        self.assertEqual(result["created"], 2)
        self.assertEqual(AttendanceRecord.objects.count(), 2)

    def test_a_record_already_stored_by_another_device_is_ignored(self):
        """Two tablets syncing the same scan must not double the attendance."""
        payload = scan_payload(self.service, "2023CS9999")

        first = sync_attendance_batch([payload], device_id="tablet-01")
        second = sync_attendance_batch([payload], device_id="tablet-02")

        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["duplicates"], 1)
        self.assertEqual(AttendanceRecord.objects.count(), 1)

    def test_malformed_uuid_is_rejected_without_losing_the_batch(self):
        payloads = [
            scan_payload(self.service, "2023CS0001"),
            {"client_uuid": "not-a-uuid", "student_identifier": "2023CS0002"},
        ]

        result = sync_attendance_batch(payloads, device_id="tablet-01")

        self.assertEqual(result["created"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(len(result["rejected"]), 1)
        self.assertEqual(AttendanceRecord.objects.count(), 1)

    def test_sync_is_audited(self):
        payloads = [scan_payload(self.service, "2023CS0001")]
        sync_attendance_batch(payloads, device_id="tablet-07")
        sync_attendance_batch(payloads, device_id="tablet-07")

        audits = list(AttendanceAudit.objects.all().order_by("id"))
        self.assertEqual(len(audits), 2)
        self.assertEqual(audits[0].created, 1)
        self.assertEqual(audits[1].created, 0)
        self.assertEqual(audits[1].duplicates, 1)

    def test_scan_for_an_unknown_hall_slot_creates_the_service(self):
        """A scan must never be lost just because the tablet was first."""
        payload = scan_payload(self.service, "2023CS4242")
        payload.pop("service_id")

        result = sync_attendance_batch([payload], device_id="tablet-01")

        self.assertEqual(result["created"], 1)
        self.assertEqual(AttendanceRecord.objects.count(), 1)
        record = AttendanceRecord.objects.first()
        self.assertEqual(record.hall_id, self.hall.id)
        self.assertEqual(record.meal, "LUNCH")
