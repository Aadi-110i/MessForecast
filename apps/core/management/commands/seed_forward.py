"""Extend the demonstration data forward into the future.

``seed_demo`` builds a history ending today. That is the right shape for
the accuracy and waste reports, which look backwards, but it leaves the
forward-looking screens — the forecast dashboard and the preparation
planning — with nothing to show.

This command carries the same three-day menu rotation past the end of the
history, creates the meal services that go with it, and then runs the real
forecasting and planning engines over them. Nothing is invented: the
forecasts come from the same code path that scores the history, and the
plans come from the same code path the kitchen uses.
"""

from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand
from django.db.models import Count, Max, Min
from django.utils import timezone

from apps.attendance.models import MealService
from apps.catalog.models import DiningHall
from apps.core.constants import MealType, PrepMode
from apps.menu.models import Menu, MenuSchedule


class Command(BaseCommand):
    help = "Extend the demo schedule and services forward, then forecast and plan them."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=14, help="Days ahead to generate.")
        parser.add_argument(
            "--skip-forecast",
            action="store_true",
            help="Only create the schedule and services; do not run the engines.",
        )

    def handle(self, *args, **options):
        days = max(1, options["days"])
        today = timezone.localdate()
        start = today
        end = today + dt.timedelta(days=days - 1)

        menus = list(Menu.objects.filter(is_active=True).order_by("code"))
        halls = list(DiningHall.objects.filter(is_active=True))
        if not menus or not halls:
            self.stderr.write("No menus or halls in the database. Run seed_demo first.")
            return

        self.stdout.write(self.style.MIGRATE_HEADING("Extending the demonstration data forward"))
        self.stdout.write(f"  window: {start} to {end}")

        created_schedules = self._create_schedules(menus, halls, start, end)
        created_services = self._create_services(start, end)
        created_codes = self._create_registration_codes(halls)

        self.stdout.write(f"  created {created_schedules} menu schedule rows")
        self.stdout.write(f"  created {created_services} meal services")
        self.stdout.write(f"  created {created_codes} registration codes")

        if options["skip_forecast"]:
            self.stdout.write(self.style.SUCCESS("Schedule extended. Run run_forecasts and build_plans next."))
            return

        self._run_engines(start, end)

    # ------------------------------------------------------------------
    # Schedule and services
    # ------------------------------------------------------------------

    def _rotation_offset(self) -> int:
        """Where the rotation stood when the history was seeded.

        The history started on a fixed day, and the cycle advances one menu
        per day. Reading the first scheduled date back tells us which
        menu the next day should take, so the rotation continues rather
        than restarting.
        """
        first = MenuSchedule.objects.order_by("date").values_list("date", flat=True).first()
        if first is None:
            return 0
        today = timezone.localdate()
        menus = Menu.objects.filter(is_active=True).order_by("code").count()
        if not menus:
            return 0
        return (today - first).days % menus

    def _create_schedules(self, menus, halls, start: dt.date, end: dt.date) -> int:
        offset = self._rotation_offset()
        existing = set(
            MenuSchedule.objects.filter(date__gte=start, date__lte=end).values_list(
                "hall_id", "date", "meal"
            )
        )

        rows = []
        current = start
        index = offset
        while current <= end:
            menu = menus[index % len(menus)]
            for hall in halls:
                for meal in MealType.values:
                    if meal == MealType.SNACK:
                        continue
                    key = (hall.id, current, meal)
                    if key in existing:
                        continue
                    rows.append(
                        MenuSchedule(
                            menu=menu,
                            hall=hall,
                            date=current,
                            meal=meal,
                            is_published=True,
                            published_at=timezone.now(),
                        )
                    )
            current += dt.timedelta(days=1)
            index += 1

        MenuSchedule.objects.bulk_create(rows, batch_size=500)
        return len(rows)

    def _create_services(self, start: dt.date, end: dt.date) -> int:
        existing = set(
            MealService.objects.filter(date__gte=start, date__lte=end).values_list(
                "hall_id", "date", "meal"
            )
        )

        rows = []
        schedules = MenuSchedule.objects.filter(date__gte=start, date__lte=end).select_related("hall")
        for schedule in schedules:
            key = (schedule.hall_id, schedule.date, schedule.meal)
            if key in existing:
                continue
            rows.append(
                MealService(
                    hall=schedule.hall,
                    date=schedule.date,
                    meal=schedule.meal,
                    registered_strength=schedule.hall.registered_strength,
                    prep_mode=PrepMode.REGISTERED_STRENGTH,
                    attendance_count=0,
                )
            )

        MealService.objects.bulk_create(rows, batch_size=500)
        return len(rows)

    # ------------------------------------------------------------------
    # Registration codes
    # ------------------------------------------------------------------

    def _create_registration_codes(self, halls) -> int:
        """Issue a few registration codes, one in each state.

        The registration console has to be readable in every state, and the
        states are reached by different actions: left alone, redeemed, pulled
        back, or left too long. These are real codes in the real table, so
        what the screen shows is what it will show in use.
        """
        from apps.accounts.models import User
        from apps.accounts.registration import RegistrationCode

        if RegistrationCode.objects.exists():
            return 0

        today = timezone.localdate()
        north = halls[0] if halls else None
        south = halls[1] if len(halls) > 1 else north

        specs = [
            (User.Role.STUDENT, north, "Aarav Menon", "21CS1044", RegistrationCode.Status.OPEN, today + dt.timedelta(days=14), "Hostel block two, second year."),
            (User.Role.KITCHEN_STAFF, south, "Ravi Shankar", "", RegistrationCode.Status.OPEN, today + dt.timedelta(days=14), "Night shift, south block."),
            (User.Role.STUDENT, north, "Fatima Qureshi", "21EC2011", RegistrationCode.Status.OPEN, today + dt.timedelta(days=14), ""),
            (User.Role.KITCHEN_STAFF, south, "Suresh Kumar", "", RegistrationCode.Status.REVOKED, today + dt.timedelta(days=14), "Issued against the wrong hall."),
            (User.Role.STUDENT, north, "Ibrahim Ali", "22CS0307", RegistrationCode.Status.OPEN, today - dt.timedelta(days=1), "Left behind at the end of term."),
        ]

        created = 0
        for role, hall, name, identifier, status, expires, notes in specs:
            code = RegistrationCode.issue(
                role,
                hall=hall,
                full_name=name,
                student_identifier=identifier,
                notes=notes,
                expires_on=expires,
            )
            if status == RegistrationCode.Status.REVOKED:
                code.status = RegistrationCode.Status.REVOKED
                code.save(update_fields=["status", "updated_at"])
            created += 1

        return created

    # ------------------------------------------------------------------
    # The real engines
    # ------------------------------------------------------------------

    def _run_engines(self, start: dt.date, end: dt.date) -> None:
        from apps.forecasting.services import generate_forecasts_for_range
        from apps.planning.services import generate_preparation_plan

        services = list(
            MealService.objects.filter(date__gte=start, date__lte=end)
            .select_related("hall")
            .order_by("date", "meal")
        )
        self.stdout.write(f"  forecasting {len(services)} services ...")
        results = generate_forecasts_for_range(start, end)
        self.stdout.write(f"  produced {len(results)} forecasts")

        plans = 0
        for service in services:
            service.refresh_from_db()
            if getattr(service, "forecast", None) is None:
                continue
            if generate_preparation_plan(service) is not None:
                plans += 1
        self.stdout.write(f"  produced {plans} preparation plans")

        self.stdout.write(self.style.SUCCESS("Forward extension complete."))
