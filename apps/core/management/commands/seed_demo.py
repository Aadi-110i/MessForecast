"""Seed the database with a realistic demonstration history.

The specification asks for a **baseline waste measurement covering at least
four weeks before deployment**, so that the saving can be evidenced. This
command builds exactly that:

* the oldest ``--baseline-weeks`` weeks are the **baseline period** — the
  kitchen cooked against the registered strength and knew nothing about
  demand;
* the remaining weeks are the **live period** — the kitchen cooked against the
  forecast.

Attendance in the live period is generated from a rule the forecaster has to
discover (weekday rhythm, exam periods, festivals, vacations), and the
forecast is generated walk-forward: each service is forecast using only the
history that existed before it. The resulting MAPE and waste cost are computed
by the platform from the records, not written into the seed.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.actuals.models import DishActual, ServiceActual
from apps.attendance.models import AttendanceRecord, MealService
from apps.catalog.models import CostRate, DiningHall, Dish, Ingredient, Recipe, RecipeItem
from apps.core import demo_data
from apps.core.constants import MealType, PrepMode
from apps.events.models import CalendarEvent, ServiceLevelConfig
from apps.forecasting.engine import BaselineForecaster, Observation
from apps.forecasting.services import EventCalendar, ServiceHistory, forecast_service
from apps.menu.models import Menu, MenuItem, MenuSchedule
from apps.planning.services import generate_preparation_plan
from apps.waste.services import compute_waste_for_actual


def deterministic_noise(seed_text: str, spread: float = 0.07) -> float:
    """A repeatable pseudo-random number in [-spread/2, +spread/2].

    Seeding from a hash keeps the dataset identical on every machine without
    relying on the random module's internal state.
    """
    digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    return (value - 0.5) * spread


class Command(BaseCommand):
    help = "Seed the database with a realistic 12-week demonstration history."

    def add_arguments(self, parser):
        parser.add_argument("--weeks", type=int, default=12, help="Total weeks of history to generate.")
        parser.add_argument("--baseline-weeks", type=int, default=4, help="Leading weeks treated as the pre-deployment baseline.")
        parser.add_argument("--reset", action="store_true", help="Delete existing demo data first.")
        parser.add_argument("--attendance-record-days", type=int, default=3, help="Days of individual scan records to materialise.")
        parser.add_argument("--students", type=int, default=700, help="Student accounts per hall.")
        parser.add_argument("--loginable-students", type=int, default=5, help="Students per hall given a usable password.")
        parser.add_argument("--seed", type=str, default="messforecast-v1", help="Seed for the reproducible parts of the dataset.")

    #: Set in ``handle`` from the command-line option.
    loginable_students = 5

    # ------------------------------------------------------------------
    @transaction.atomic
    def handle(self, *args, **options):
        self.loginable_students = options["loginable_students"]
        weeks = options["weeks"]
        baseline_weeks = min(options["baseline_weeks"], weeks)
        today = timezone.localdate()
        start = today - dt.timedelta(days=weeks * 7 - 1)
        baseline_end = start + dt.timedelta(weeks=baseline_weeks) - dt.timedelta(days=1)
        live_start = baseline_end + dt.timedelta(days=1)

        self.stdout.write(self.style.MIGRATE_HEADING("Seeding MessForecast demonstration data"))
        self.stdout.write(f"  history window : {start} to {today}  ({weeks} weeks)")
        self.stdout.write(f"  baseline period: {start} to {baseline_end}  ({baseline_weeks} weeks, registered-strength cooking)")
        self.stdout.write(f"  live period    : {live_start} to {today}  ({weeks - baseline_weeks} weeks, forecast-guided cooking)")

        if options["reset"]:
            self._reset()

        halls = self._create_halls()
        ingredients = self._create_ingredients()
        dishes = self._create_dishes(ingredients)
        menus = self._create_menus(dishes)
        self._create_service_levels()
        users = self._create_users(halls, options["students"])
        events = self._create_events(today, start)
        self._create_schedules(menus, halls, start, today)
        services = self._create_services(halls, start, today)

        self.stdout.write("  generating attendance, forecasts, plans and actuals ...")
        self._run_history(
            services=services,
            halls=halls,
            menus=menus,
            dishes=dishes,
            events=events,
            start=start,
            today=today,
            baseline_end=baseline_end,
            seed=options["seed"],
        )

        if options["attendance_record_days"] > 0:
            self.stdout.write("  materialising individual scan records ...")
            self._create_attendance_records(services, users, halls, today, options["attendance_record_days"], options["seed"])

        self._report(start, today, baseline_end, live_start)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def _reset(self):
        self.stdout.write("  removing existing demo data ...")
        from apps.planning.models import IngredientIndent, PreparationLine, PreparationPlan
        from apps.waste.models import WasteRecord
        from apps.forecasting.models import Forecast
        from apps.notifications.models import Notification

        WasteRecord.objects.all().delete()
        DishActual.objects.all().delete()
        ServiceActual.objects.all().delete()
        IngredientIndent.objects.all().delete()
        PreparationLine.objects.all().delete()
        PreparationPlan.objects.all().delete()
        Forecast.objects.all().delete()
        Notification.objects.all().delete()
        AttendanceRecord.objects.all().delete()
        MealService.objects.all().delete()
        MenuSchedule.objects.all().delete()
        MenuItem.objects.all().delete()
        Menu.objects.all().delete()
        CalendarEvent.objects.all().delete()
        ServiceLevelConfig.objects.all().delete()
        RecipeItem.objects.all().delete()
        Recipe.objects.all().delete()
        CostRate.objects.all().delete()
        Dish.objects.all().delete()
        Ingredient.objects.all().delete()
        DiningHall.objects.all().delete()

    def _create_halls(self) -> dict:
        halls = {}
        for spec in demo_data.HALLS:
            hall, _ = DiningHall.objects.update_or_create(
                code=spec["code"],
                defaults={
                    "name": spec["name"],
                    "location": spec.get("location", ""),
                    "capacity": spec["capacity"],
                    "registered_strength": spec["registered_strength"],
                    "notes": spec["notes"],
                    "is_active": True,
                },
            )
            halls[spec["code"]] = hall
        return halls

    def _create_ingredients(self) -> dict:
        ingredients = {}
        for code, name, unit, cost, pack, category in demo_data.INGREDIENTS:
            ingredient, _ = Ingredient.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "base_unit": unit,
                    "purchase_pack_size": Decimal(pack),
                    "purchase_pack_unit": f"{pack} {unit}",
                    "category": category,
                    "is_active": True,
                },
            )
            CostRate.objects.update_or_create(
                ingredient=ingredient,
                hall=None,
                effective_from=dt.date(2026, 1, 1),
                defaults={"unit_cost": Decimal(cost), "source": "Demo procurement rate"},
            )
            ingredients[code] = ingredient
        return ingredients

    def _create_dishes(self, ingredients: dict) -> dict:
        dishes = {}
        for code, name, category, serving, recipe_lines in demo_data.DISHES:
            dish, _ = Dish.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "category": category,
                    "serving_size_g": Decimal(serving),
                    "is_active": True,
                },
            )
            recipe, _ = Recipe.objects.update_or_create(
                dish=dish,
                version=1,
                defaults={"effective_from": dt.date(2026, 1, 1), "is_active": True},
            )
            recipe.items.all().delete()
            for ingredient_code, quantity, trim in recipe_lines:
                RecipeItem.objects.create(
                    recipe=recipe,
                    ingredient=ingredients[ingredient_code],
                    quantity=Decimal(quantity),
                    trim_loss_pct=Decimal(trim),
                )
            dishes[code] = dish
        return dishes

    def _create_menus(self, dishes: dict) -> dict:
        menus = {}
        for spec in demo_data.MENUS:
            menu, _ = Menu.objects.update_or_create(
                code=spec["code"],
                defaults={
                    "name": spec["name"],
                    "cycle_label": spec["cycle_label"],
                    "description": spec["description"],
                    "is_active": True,
                },
            )
            menu.items.all().delete()
            for meal, dish_codes in spec["items"].items():
                for sequence, dish_code in enumerate(dish_codes):
                    MenuItem.objects.create(
                        menu=menu,
                        meal=meal,
                        dish=dishes[dish_code],
                        sequence=sequence,
                        expected_share=Decimal("0"),  # unknown until the actuals teach it
                    )
            menus[spec["code"]] = menu
        return menus

    def _create_service_levels(self):
        ServiceLevelConfig.objects.update_or_create(
            hall=None, meal=None, effective_from=dt.date(2026, 1, 1),
            defaults={
                "acceptable_overprep_pct": Decimal(demo_data.LIVE_OVERPREPARATION_PCT),
                "max_overprep_pct": Decimal("18.00"),
                "min_buffer_portions": 20,
                "portions_per_student": Decimal("2.40"),
                "notes": "Default: the platform's standard over-preparation allowance.",
            },
        )
        for meal, ratio in demo_data.PORTIONS_PER_STUDENT.items():
            ServiceLevelConfig.objects.update_or_create(
                hall=None, meal=meal, effective_from=dt.date(2026, 1, 1),
                defaults={
                    "acceptable_overprep_pct": Decimal(demo_data.LIVE_OVERPREPARATION_PCT),
                    "max_overprep_pct": Decimal("18.00"),
                    "min_buffer_portions": 15,
                    "portions_per_student": Decimal(ratio),
                    "notes": f"Default portions per student for {meal.lower()}.",
                },
            )

    def _create_users(self, halls: dict, students_per_hall: int) -> dict:
        users = {}
        for username, role, first, last, hall_code in demo_data.DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "role": role,
                    "first_name": first,
                    "last_name": last,
                    "email": f"{username}@campus.example",
                    "hall": halls.get(hall_code) if hall_code else None,
                    "is_staff": role in {"ADMINISTRATOR", "MESS_MANAGER", "MESS_ADMIN"},
                },
            )
            if created:
                user.set_password(demo_data.DEMO_PASSWORD)
                user.save()
            users[username] = user

        rng = random.Random(20261105)
        student_pools = {}
        for hall_code, hall in halls.items():
            pool = []
            for index in range(students_per_hall):
                identifier = f"{hall_code[:1]}{rng.randint(100000, 999999)}"
                user, created = User.objects.get_or_create(
                    student_identifier=identifier,
                    defaults={
                        "username": f"student_{hall_code.lower()}_{identifier}",
                        "role": User.Role.STUDENT,
                        "first_name": "Student",
                        "last_name": identifier,
                        "hall": hall,
                    },
                )
                # Student accounts are attendance identities, not logins. Only a
                # handful get a usable password: hashing is deliberately slow,
                # and hashing fourteen hundred of them would take longer than
                # the rest of the seed put together.
                if created and index < self.loginable_students:
                    user.set_password(demo_data.DEMO_PASSWORD)
                    user.save(update_fields=["password"])
                pool.append(user)
            student_pools[hall_code] = pool
        return {"demo": users, "students": student_pools}

    def _create_events(self, today: dt.date, start: dt.date) -> list:
        events = []
        for spec in demo_data.EVENTS:
            event_start = today + dt.timedelta(days=spec["offset_start"])
            event_end = today + dt.timedelta(days=spec["offset_end"])
            if event_end < start:
                continue
            event, _ = CalendarEvent.objects.update_or_create(
                name=spec["name"],
                defaults={
                    "event_type": spec["event_type"],
                    "start_date": event_start,
                    "end_date": event_end,
                    "impact_factor": Decimal(spec["impact_factor"]),
                    "affects_meals": spec["meals"],
                    "description": spec["description"],
                    "is_active": True,
                },
            )
            events.append(event)
        return events

    def _create_schedules(self, menus: dict, halls: dict, start: dt.date, end: dt.date):
        """A three-day menu rotation across the whole window."""
        menu_codes = list(menus.keys())
        rows = []
        current = start
        index = 0
        while current <= end:
            menu_code = menu_codes[index % len(menu_codes)]
            for hall in halls.values():
                for meal in MealType.values:
                    if meal == MealType.SNACK:
                        continue
                    rows.append(
                        MenuSchedule(
                            menu=menus[menu_code],
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
        self.stdout.write(f"  created {len(rows)} menu schedule rows")

    def _create_services(self, halls: dict, start: dt.date, end: dt.date) -> dict:
        """One meal service per (hall, date, meal) across the window."""
        rows = []
        schedules = MenuSchedule.objects.filter(date__gte=start, date__lte=end).select_related("hall")
        for schedule in schedules:
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
        self.stdout.write(f"  created {len(rows)} meal services")
        return {"count": len(rows)}

    # ------------------------------------------------------------------
    # The history sweep
    # ------------------------------------------------------------------
    def _run_history(self, services, halls, menus, dishes, events, start, today, baseline_end, seed):
        forecaster = BaselineForecaster(decay=0.85, confidence=0.80, min_history=6)
        event_calendar = EventCalendar(list(events))

        # Observations per (hall, meal), kept in memory as we sweep forward.
        history: dict[tuple, list[Observation]] = {}
        # Learned dish shares per (menu code, meal).
        learned: dict[tuple, dict[str, Decimal]] = {}
        learned_counts: dict[tuple, int] = {}
        # Service-level configuration is fixed for the whole seed.
        levels: dict[tuple, ServiceLevelConfig] = {}

        # Every schedule in the window, fetched once.
        schedules = {
            (schedule.hall_id, schedule.date, schedule.meal): schedule
            for schedule in MenuSchedule.objects.filter(
                date__gte=start, date__lte=today
            ).select_related("menu", "hall").prefetch_related("menu__items__dish")
        }

        services_qs = (
            MealService.objects.filter(date__gte=start, date__lte=today)
            .select_related("hall")
            .order_by("date", "meal", "hall")
        )

        processed = 0
        total = services_qs.count()

        for service in services_qs:
            schedule = schedules.get((service.hall_id, service.date, service.meal))
            menu_code = schedule.menu.code if schedule else None

            factor, _names = event_calendar.factor(service.date, service.meal, service.hall)
            attendance = self._attendance_for(service, factor, seed)

            service.attendance_count = attendance
            service.prep_mode = (
                PrepMode.FORECAST_GUIDED
                if service.date > baseline_end
                else PrepMode.REGISTERED_STRENGTH
            )
            service.save(update_fields=["attendance_count", "prep_mode"])

            key = (service.hall_id, service.meal)
            observations = history.setdefault(key, [])

            # --- Live period: forecast first, then plan, then cook --------
            plan = None
            forecast = None
            if service.date > baseline_end:
                level_key = (service.hall_id, service.meal)
                if level_key not in levels:
                    levels[level_key] = ServiceLevelConfig.resolve(
                        service.hall, service.meal, service.date
                    )

                service_history = ServiceHistory(
                    hall=service.hall,
                    meal=service.meal,
                    observations=list(observations),
                    event_calendar=event_calendar,
                )
                forecast = forecast_service(service, forecaster, history=service_history)
                plan = self._build_plan(
                    service, service.forecast, levels[level_key],
                    shares=self._resolved_shares(schedule, service.meal, learned),
                )

            # --- What the kitchen actually did ----------------------------
            prepared_portions = self._prepared_portions(service, plan, factor, seed)
            served_portions = int(round(attendance * self._portions_per_student(service.meal)))

            actual = self._record_actual(service, plan, prepared_portions, served_portions, schedule)
            if actual is not None:
                self._learn_from_actual(learned, learned_counts, menu_code, service.meal, actual)

            observations.append(
                Observation(
                    date=service.date,
                    attendance=attendance,
                    event_factor=factor,
                    is_exam_period=any(
                        e.covers(service.date) and e.event_type == "EXAM" for e in events
                    ),
                )
            )
            processed += 1
            if processed % 100 == 0:
                self.stdout.write(f"    {processed}/{total} services ...")

        self.stdout.write(f"    {processed}/{total} services complete")
        # Write the learned shares back onto the menu, so the running system
        # starts from what the history taught it.
        self._apply_learned_shares(menus, learned)

    def _resolved_shares(self, schedule, meal, learned):
        """The share of portions each dish should get, from what was learned."""
        if schedule is None:
            return None
        key = (schedule.menu.code, meal)
        learned_map = learned.get(key)
        if not learned_map:
            return None
        items = list(schedule.menu.items_for_meal(meal))
        raw = [Decimal(learned_map.get(item.dish.code, 0)) for item in items]
        total = sum(raw, Decimal("0"))
        if total <= 0:
            return None
        return [value / total for value in raw]

    def _attendance_for(self, service, event_factor: Decimal, seed: str) -> int:
        rate = Decimal(demo_data.MEAL_ATTENDANCE_RATE[service.meal])
        weekday = Decimal(demo_data.WEEKDAY_MULTIPLIER[service.date.weekday()])
        base = Decimal(service.registered_strength) * rate * weekday * event_factor
        noise = deterministic_noise(
            f"{seed}|{service.hall.code}|{service.date.isoformat()}|{service.meal}", 0.07
        )
        return max(0, int(round(float(base) * (1 + noise))))

    def _portions_per_student(self, meal: str) -> Decimal:
        return Decimal(demo_data.PORTIONS_PER_STUDENT.get(meal, "2.40"))

    def _prepared_portions(self, service, plan, event_factor, seed) -> int:
        """How many portions the kitchen actually prepared.

        In the baseline period the kitchen cooked against the registered
        strength with a comfortable 16% buffer and no idea what the day would
        bring. In the live period it cooked against the forecast.
        """
        portions_per_student = self._portions_per_student(service.meal)
        if plan is not None:
            planned = Decimal(plan.portions_to_prepare)
        else:
            rate = Decimal(demo_data.MEAL_ATTENDANCE_RATE[service.meal])
            weekday = Decimal(demo_data.WEEKDAY_MULTIPLIER[service.date.weekday()])
            planned = (
                Decimal(service.registered_strength) * rate * weekday * portions_per_student
                * Decimal(demo_data.BASELINE_OVERPREPARATION)
            )
        # A little kitchen variance: nobody measures to the gram.
        variance = deterministic_noise(
            f"{seed}|prep|{service.hall.code}|{service.date.isoformat()}|{service.meal}", 0.04
        )
        return max(0, int(round(float(planned) * (1 + variance))))

    def _build_plan(self, service, forecast, level, shares=None):
        try:
            return generate_preparation_plan(
                service, forecast=forecast, service_level=level, shares=shares
            )
        except Exception as exc:  # pragma: no cover - defensive
            self.stderr.write(f"    plan failed for {service}: {exc}")
            return None

    def _record_actual(self, service, plan, prepared_portions, served_portions, schedule):
        if schedule is None:
            return None
        items = list(schedule.menu.items_for_meal(service.meal).select_related("dish"))

        # Split the served portions across the dishes in proportion to what
        # students actually take (the popularity weights).
        weights = [Decimal(demo_data.DISH_POPULARITY.get(item.dish.code, "0.50")) for item in items]
        weight_total = sum(weights, Decimal("0"))
        if weight_total <= 0:
            weights = [Decimal("1")] * len(items)
            weight_total = Decimal(len(items))

        actual = ServiceActual.objects.create(
            service=service,
            prepared_portions_total=prepared_portions,
            served_portions_total=served_portions,
            leftover_portions_total=max(0, prepared_portions - served_portions),
            prep_mode=(
                PrepMode.FORECAST_GUIDED if plan is not None else PrepMode.REGISTERED_STRENGTH
            ),
            attendance_actual=service.attendance_count,
            recorded_by=None,
        )

        allocated = 0
        lines = []
        for index, (item, weight) in enumerate(zip(items, weights)):
            share = weight / weight_total
            served = int(round(served_portions * float(share)))
            if index == len(items) - 1:
                served = max(0, served_portions - allocated)
            allocated += served
            lines.append(
                DishActual(
                    service_actual=actual,
                    dish=item.dish,
                    prepared_portions=int(round(prepared_portions * float(share))),
                    served_portions=served,
                    leftover_portions=0,
                )
            )
        DishActual.objects.bulk_create(lines, batch_size=50)
        for line in lines:
            line.leftover_portions = max(0, line.prepared_portions - line.served_portions)
            line.save(update_fields=["leftover_portions"])

        compute_waste_for_actual(actual)
        return actual

    # ------------------------------------------------------------------
    # Dish-share learning
    # ------------------------------------------------------------------
    def _apply_learned_shares(self, menus, learned):
        """Write the learned shares back onto the menu items."""
        for (menu_code, meal), shares in learned.items():
            menu = menus.get(menu_code)
            if menu is None:
                continue
            for item in menu.items.filter(meal=meal):
                value = shares.get(item.dish.code)
                if value is not None:
                    item.expected_share = value
                    item.save(update_fields=["expected_share"])

    def _learn_from_actual(self, learned, learned_counts, menu_code, meal, actual):
        """Update the running average of what students actually took."""
        if not menu_code:
            return
        key = (menu_code, meal)
        totals = learned.setdefault(key, {})
        served_by_dish = {}
        total_served = 0
        for dish_actual in actual.dish_actuals.all():
            served_by_dish[dish_actual.dish.code] = dish_actual.served_portions
            total_served += dish_actual.served_portions
        if total_served <= 0:
            return
        n = learned_counts.get(key, 0) + 1
        learned_counts[key] = n
        for dish_code, served in served_by_dish.items():
            share = Decimal(served) / Decimal(total_served)
            previous = totals.get(dish_code, Decimal("0"))
            totals[dish_code] = (previous * Decimal(n - 1) + share) / Decimal(n)

    # ------------------------------------------------------------------
    # Individual scan records
    # ------------------------------------------------------------------
    def _create_attendance_records(self, services, users, halls, today, days, seed):
        rng = random.Random(20261105)
        start = today - dt.timedelta(days=days - 1)
        services_qs = (
            MealService.objects.filter(date__gte=start, date__lte=today)
            .select_related("hall")
            .order_by("date", "meal", "hall")
        )
        pools = users["students"]
        rows = []
        for service in services_qs:
            pool = pools.get(service.hall.code, [])
            if not pool:
                continue
            count = min(service.attendance_count, len(pool))
            chosen = rng.sample(pool, count) if count else []
            captured = timezone.make_aware(
                dt.datetime.combine(service.date, dt.time(hour=8))
                + dt.timedelta(hours={"BREAKFAST": 0, "LUNCH": 5, "DINNER": 9}.get(service.meal, 1)),
                timezone.get_current_timezone(),
            )
            for student in chosen:
                rows.append(
                    AttendanceRecord(
                        service=service,
                        hall=service.hall,
                        meal=service.meal,
                        student=student,
                        student_identifier=student.student_identifier,
                        method="QR",
                        captured_at=captured,
                        device_id="tablet-north-01",
                        captured_offline=False,
                        synced_at=captured,
                    )
                )
        AttendanceRecord.objects.bulk_create(rows, batch_size=2000)
        self.stdout.write(f"  created {len(rows)} attendance records")

    # ------------------------------------------------------------------
    def _report(self, start, today, baseline_end, live_start):
        from apps.reporting.services import accuracy_summary, baseline_comparison, exact_mape
        from apps.waste.services import average_waste_cost_per_service, waste_totals

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Baseline measurement (the pre-deployment figure)"))
        baseline = waste_totals(start, baseline_end)
        baseline_per_service = average_waste_cost_per_service(start, baseline_end)
        self.stdout.write(f"  waste cost      : Rs {baseline['waste_cost']}")
        self.stdout.write(f"  waste weight    : {baseline['waste_quantity_kg']} kg")
        self.stdout.write(f"  per service     : Rs {baseline_per_service}")

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Live period (forecast-guided)"))
        live = waste_totals(live_start, today)
        live_per_service = average_waste_cost_per_service(live_start, today)
        self.stdout.write(f"  waste cost      : Rs {live['waste_cost']}")
        self.stdout.write(f"  waste weight    : {live['waste_quantity_kg']} kg")
        self.stdout.write(f"  per service     : Rs {live_per_service}")

        comparison = baseline_comparison(start, baseline_end, live_start, today)
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Measured improvement"))
        self.stdout.write(f"  saving per service : Rs {comparison['saving_per_service']}")
        self.stdout.write(f"  reduction          : {comparison['saving_pct']}%")
        self.stdout.write(f"  annualised         : Rs {comparison['annualised_saving']}")

        accuracy = accuracy_summary(live_start, today)
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Forecast accuracy over the live period"))
        self.stdout.write(f"  MAPE          : {exact_mape(live_start, today)}%")
        self.stdout.write(f"  forecasts     : {accuracy['forecasts']}")
        self.stdout.write(f"  range coverage: {accuracy['coverage_pct']}%")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Seed complete."))
