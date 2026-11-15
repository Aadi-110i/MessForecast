"""Turn forecasts into preparation plans and ingredient indents."""

from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.attendance.models import MealService
from apps.planning.services import PlanningError, generate_preparation_plan


class Command(BaseCommand):
    help = "Build preparation plans (and ingredient indents) from the current forecasts."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=2, help="How many days ahead to plan.")
        parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD). Defaults to today.")
        parser.add_argument("--publish", action="store_true", help="Mark the plans as published to the kitchen.")

    def handle(self, *args, **options):
        start = (
            dt.date.fromisoformat(options["start"])
            if options["start"]
            else timezone.localdate()
        )
        end = start + dt.timedelta(days=options["days"])

        services = (
            MealService.objects.filter(date__gte=start, date__lte=end)
            .select_related("hall", "forecast")
            .prefetch_related("preparation_plan")
        )

        built = 0
        skipped = []
        for service in services:
            if getattr(service, "forecast", None) is None:
                skipped.append(f"{service}: no forecast")
                continue
            try:
                plan = generate_preparation_plan(service)
                if options["publish"]:
                    plan.status = "PUBLISHED"
                    plan.save(update_fields=["status"])
                built += 1
            except PlanningError as exc:
                skipped.append(f"{service}: {exc}")

        self.stdout.write(self.style.MIGRATE_HEADING(f"Planning {start} to {end}"))
        self.stdout.write(f"  plans built : {built}")
        self.stdout.write(f"  skipped     : {len(skipped)}")
        for reason in skipped[:10]:
            self.stdout.write(f"    - {reason}")
        self.stdout.write(self.style.SUCCESS("Planning complete."))
