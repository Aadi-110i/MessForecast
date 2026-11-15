"""Produce the rolling forecast.

The specification asks for a 7-day forecast generated daily. This command is
what the Celery task calls, and it can be run by hand for the same effect.
"""

from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.forecasting.services import generate_forecasts_for_range


class Command(BaseCommand):
    help = "Generate forecasts for every scheduled service in a date range."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7, help="Number of days ahead to forecast.")
        parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD). Defaults to today.")
        parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD). Overrides --days.")

    def handle(self, *args, **options):
        start = (
            dt.date.fromisoformat(options["start"])
            if options["start"]
            else timezone.localdate()
        )
        end = (
            dt.date.fromisoformat(options["end"])
            if options["end"]
            else start + dt.timedelta(days=options["days"])
        )

        results = generate_forecasts_for_range(start, end)

        self.stdout.write(self.style.MIGRATE_HEADING(f"Forecasting {start} to {end}"))
        fallbacks = sum(1 for r in results if r.fallback_used)
        self.stdout.write(f"  forecasts generated : {len(results)}")
        self.stdout.write(f"  cold-start fallbacks: {fallbacks}")
        for result in results[:12]:
            self.stdout.write(
                f"  {result.method}  point={result.point_estimate}  "
                f"range={result.lower_bound}-{result.upper_bound}  "
                f"mape={result.mape}  obs={result.observations_used}"
            )
        if len(results) > 12:
            self.stdout.write(f"  ... and {len(results) - 12} more")
        self.stdout.write(self.style.SUCCESS("Forecasts complete."))
