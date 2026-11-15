"""Import students and registered strength from the ERP.

The specification names the ERP as the source of student registration and mess
fee category. This command takes a simple CSV - the shape most ERPs can export
- and loads it.

CSV columns (the first two are required)::

    credential,hall,registered,fee_category,name,year

    2023CS0142,NORTH,1,HOSTEL,Maya Iyer,3
"""

from __future__ import annotations

import csv
import sys

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.catalog.models import DiningHall


class Command(BaseCommand):
    help = "Import student registration from the ERP export (CSV on stdin or a file path)."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", nargs="?", default=None, help="CSV file. Reads stdin when omitted.")

    @transaction.atomic
    def handle(self, *args, **options):
        path = options["csv_path"]
        stream = open(path, newline="", encoding="utf-8-sig") if path else sys.stdin
        try:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or "credential" not in reader.fieldnames:
                raise CommandError("The CSV must have a 'credential' column.")

            created = 0
            updated = 0
            skipped = 0
            hall_cache: dict[str, DiningHall] = {}

            for row in reader:
                credential = (row.get("credential") or "").strip()
                if not credential:
                    skipped += 1
                    continue

                hall = None
                hall_code = (row.get("hall") or "").strip().upper()
                if hall_code:
                    if hall_code not in hall_cache:
                        hall_cache[hall_code] = DiningHall.objects.filter(code=hall_code).first()
                    hall = hall_cache[hall_code]

                registered = str(row.get("registered", "1")).strip().lower() in {"1", "true", "yes", "y"}
                defaults = {
                    "role": User.Role.STUDENT,
                    "first_name": (row.get("name") or "").split(" ")[0][:150],
                    "last_name": " ".join((row.get("name") or "").split(" ")[1:])[:150],
                    "hall": hall,
                    "is_active": registered,
                    "email": "",
                }
                user, was_created = User.objects.get_or_create(
                    student_identifier=credential, defaults=defaults
                )
                if was_created:
                    created += 1
                else:
                    for key, value in defaults.items():
                        if key != "email":
                            setattr(user, key, value)
                    user.save()
                    updated += 1

            self.stdout.write(self.style.SUCCESS(
                f"ERP import complete: {created} created, {updated} updated, {skipped} skipped."
            ))
        finally:
            if path:
                stream.close()
