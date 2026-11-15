"""Measure baseline waste for a period.

The specification requires a baseline waste measurement covering at least four
weeks before deployment, so that the saving can be evidenced. This command
produces that figure from the recorded services, and prints the comparison
against a live period.
"""

from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.reporting.services import baseline_comparison, saving_trend_by_week
from apps.waste.services import (
    average_waste_cost_per_service,
    top_waste_dishes,
    waste_by_meal,
    waste_by_week,
    waste_totals,
)


class Command(BaseCommand):
    help = "Measure waste over a period and compare it with a live period."

    def add_arguments(self, parser):
        parser.add_argument("--start", type=str, required=True, help="Baseline start date (YYYY-MM-DD).")
        parser.add_argument("--end", type=str, required=True, help="Baseline end date (YYYY-MM-DD).")
        parser.add_argument("--live-start", type=str, default=None, help="Live period start date.")
        parser.add_argument("--live-end", type=str, default=None, help="Live period end date.")
        parser.add_argument("--hall", type=int, default=None, help="Restrict to one dining hall id.")
        parser.add_argument("--json", action="store_true", help="Emit the figures as JSON.")

    def handle(self, *args, **options):
        try:
            start = dt.date.fromisoformat(options["start"])
            end = dt.date.fromisoformat(options["end"])
        except ValueError as exc:
            raise CommandError("Dates must be in YYYY-MM-DD format.") from exc

        if end < start:
            raise CommandError("The end date is before the start date.")

        hall = options["hall"]
        totals = waste_totals(start, end, hall)

        if options["json"]:
            import json

            self.stdout.write(
                json.dumps(
                    {
                        "baseline_start": start.isoformat(),
                        "baseline_end": end.isoformat(),
                        "waste_cost": str(totals["waste_cost"]),
                        "waste_quantity_kg": str(totals["waste_quantity_kg"]),
                        "records": totals["records"],
                        "per_service": str(average_waste_cost_per_service(start, end, hall)),
                    },
                    indent=2,
                )
            )
            return

        self.stdout.write(self.style.MIGRATE_HEADING(f"Baseline waste measurement  {start} to {end}"))
        self.stdout.write(f"  waste cost        : Rs {totals['waste_cost']}")
        self.stdout.write(f"  waste weight      : {totals['waste_quantity_kg']} kg")
        self.stdout.write(f"  dish records      : {totals['records']}")
        self.stdout.write(f"  cost per service  : Rs {average_waste_cost_per_service(start, end, hall)}")
        self.stdout.write("  by meal:")
        for row in waste_by_meal(start, end, hall):
            self.stdout.write(f"    {row['meal']:<10} Rs {row['waste_cost']:<10} {row['waste_quantity_kg']} kg")
        self.stdout.write("  by week:")
        for row in waste_by_week(start, end, hall):
            self.stdout.write(f"    {row['week']}  Rs {row['waste_cost']}")
        self.stdout.write("  worst dishes:")
        for row in top_waste_dishes(start, end, hall, limit=5):
            self.stdout.write(f"    {row['dish']:<28} Rs {row['waste_cost']}")

        if options["live_start"] and options["live_end"]:
            live_start = dt.date.fromisoformat(options["live_start"])
            live_end = dt.date.fromisoformat(options["live_end"])
            comparison = baseline_comparison(start, end, live_start, live_end, hall)
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING(f"Comparison against the live period  {live_start} to {live_end}"))
            self.stdout.write(f"  baseline per service : Rs {comparison['baseline']['waste_cost']} over {comparison['baseline']['services']} services")
            self.stdout.write(f"  live per service     : Rs {comparison['live']['waste_cost']} over {comparison['live']['services']} services")
            self.stdout.write(f"  saving per service   : Rs {comparison['saving_per_service']}")
            self.stdout.write(f"  reduction            : {comparison['saving_pct']}%")
            self.stdout.write(f"  annualised           : Rs {comparison['annualised_saving']}")
            self.stdout.write("")
            self.stdout.write("  weekly trend:")
            for row in saving_trend_by_week(start, end, live_start, live_end, hall):
                self.stdout.write(
                    f"    {row['week']}  {row['period']:<9} Rs {row['waste_cost_per_service']:<9} per service"
                )
        self.stdout.write(self.style.SUCCESS("Baseline measurement complete."))
