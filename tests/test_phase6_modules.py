"""Tests for the Phase 6 core modules.

The specification for Phase 6 asks for four modules: menu management,
recipes and ingredients, attendance, and the calendar. Most of it existed
before this phase, so these tests cover the two things that were wrong -
deleting a record the history holds, and replacing a meal that is already
scheduled - and the three things that were missing: daily menus, weekly
menus, and editing the masters from the console.

Every test drives a real request against a real database.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.models import Dish
from apps.core.constants import MealType
from apps.events.models import CalendarEvent
from apps.menu.models import Menu, MenuSchedule

from .factories import (
    add_dish_to_menu,
    make_actual,
    make_dish,
    make_hall,
    make_menu,
    make_service,
    make_user,
    schedule_menu,
)


class ScheduleReplaceTests(TestCase):
    """Replacing a meal that is already scheduled must not be a server error.

    The slot is unique on (hall, date, meal), so the row is found by those
    three fields and the cycle on it is changed.
    """

    def setUp(self):
        self.manager = make_user("manager", User.Role.MESS_MANAGER)
        self.hall = make_hall()
        self.first = make_menu("MENU_A", "Menu Cycle A")
        self.second = make_menu("MENU_B", "Menu Cycle B")
        self.on_date = dt.date(2026, 11, 9)
        schedule_menu(self.first, self.hall, self.on_date, "LUNCH")
        self.client.force_login(self.manager)

    def test_replacing_a_scheduled_meal_replaces_it(self):
        response = self.client.post(
            reverse("console-schedule-assign"),
            {
                "menu": self.second.pk,
                "hall": self.hall.pk,
                "date": self.on_date.isoformat(),
                "meal": "LUNCH",
            },
        )
        self.assertEqual(response.status_code, 302)
        row = MenuSchedule.objects.get(hall=self.hall, date=self.on_date, meal="LUNCH")
        self.assertEqual(row.menu_id, self.second.pk)

    def test_replacing_a_scheduled_meal_does_not_duplicate_it(self):
        self.client.post(
            reverse("console-schedule-assign"),
            {
                "menu": self.second.pk,
                "hall": self.hall.pk,
                "date": self.on_date.isoformat(),
                "meal": "LUNCH",
            },
        )
        self.assertEqual(
            MenuSchedule.objects.filter(hall=self.hall, date=self.on_date, meal="LUNCH").count(),
            1,
        )

    def test_a_published_slot_stays_published_when_it_is_replaced(self):
        self.client.post(
            reverse("console-schedule-assign"),
            {
                "menu": self.second.pk,
                "hall": self.hall.pk,
                "date": self.on_date.isoformat(),
                "meal": "LUNCH",
            },
        )
        row = MenuSchedule.objects.get(hall=self.hall, date=self.on_date, meal="LUNCH")
        self.assertTrue(row.is_published)

    def test_a_missing_date_is_a_redirect_with_a_message(self):
        response = self.client.post(
            reverse("console-schedule-assign"),
            {"menu": self.first.pk, "hall": self.hall.pk, "date": "", "meal": "LUNCH"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("error=", response.url)

    def test_an_unknown_meal_is_refused(self):
        response = self.client.post(
            reverse("console-schedule-assign"),
            {
                "menu": self.first.pk,
                "hall": self.hall.pk,
                "date": self.on_date.isoformat(),
                "meal": "BRUNCH",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            MenuSchedule.objects.filter(hall=self.hall, meal="BRUNCH").exists()
        )


class DailyMenuTests(TestCase):
    """A daily menu writes every meal of one hall on one date."""

    def setUp(self):
        self.manager = make_user("manager", User.Role.MESS_MANAGER)
        self.hall = make_hall()
        self.menu = make_menu()
        self.on_date = dt.date(2026, 11, 9)
        self.client.force_login(self.manager)

    def test_the_day_writes_every_meal(self):
        response = self.client.post(
            reverse("console-schedule-day"),
            {"menu": self.menu.pk, "hall": self.hall.pk, "date": self.on_date.isoformat()},
        )
        self.assertEqual(response.status_code, 302)
        written = MenuSchedule.objects.filter(hall=self.hall, date=self.on_date)
        self.assertEqual(written.count(), len(MealType))
        for meal in MealType:
            self.assertTrue(written.filter(meal=meal.value).exists(), meal.value)

    def test_the_day_includes_the_snack(self):
        self.client.post(
            reverse("console-schedule-day"),
            {"menu": self.menu.pk, "hall": self.hall.pk, "date": self.on_date.isoformat()},
        )
        self.assertTrue(
            MenuSchedule.objects.filter(
                hall=self.hall, date=self.on_date, meal=MealType.SNACK.value
            ).exists()
        )

    def test_the_day_is_idempotent(self):
        for _ in range(2):
            self.client.post(
                reverse("console-schedule-day"),
                {"menu": self.menu.pk, "hall": self.hall.pk, "date": self.on_date.isoformat()},
            )
        self.assertEqual(
            MenuSchedule.objects.filter(hall=self.hall, date=self.on_date).count(),
            len(MealType),
        )


class WeeklyMenuTests(TestCase):
    """A weekly menu writes a rotation of cycles across seven days."""

    def setUp(self):
        self.manager = make_user("manager", User.Role.MESS_MANAGER)
        self.hall = make_hall()
        self.first = make_menu("MENU_A", "Menu Cycle A")
        self.second = make_menu("MENU_B", "Menu Cycle B")
        self.third = make_menu("MENU_C", "Menu Cycle C")
        # A Wednesday, so the week starts on the Monday before it.
        self.start = dt.date(2026, 11, 11)
        self.client.force_login(self.manager)

    def test_the_week_writes_seven_days(self):
        response = self.client.post(
            reverse("console-schedule-week"),
            {
                "hall": self.hall.pk,
                "start": self.start.isoformat(),
                "cycles": [self.first.pk, self.second.pk, self.third.pk],
            },
        )
        self.assertEqual(response.status_code, 302)
        days = MenuSchedule.objects.filter(hall=self.hall).values_list("date", flat=True)
        self.assertEqual(len(set(days)), 7)

    def test_the_week_starts_on_the_monday(self):
        self.client.post(
            reverse("console-schedule-week"),
            {"hall": self.hall.pk, "start": self.start.isoformat(), "cycles": [self.first.pk]},
        )
        first_day = MenuSchedule.objects.filter(hall=self.hall).order_by("date").first()
        self.assertEqual(first_day.date, dt.date(2026, 11, 9))
        self.assertEqual(first_day.date.weekday(), 0)

    def test_the_rotation_repeats(self):
        self.client.post(
            reverse("console-schedule-week"),
            {
                "hall": self.hall.pk,
                "start": self.start.isoformat(),
                "cycles": [self.first.pk, self.second.pk, self.third.pk],
            },
        )
        by_date = {
            row.date: row.menu_id
            for row in MenuSchedule.objects.filter(hall=self.hall, meal="BREAKFAST")
        }
        monday = dt.date(2026, 11, 9)
        self.assertEqual(by_date[monday], self.first.pk)
        self.assertEqual(by_date[monday + dt.timedelta(days=1)], self.second.pk)
        self.assertEqual(by_date[monday + dt.timedelta(days=2)], self.third.pk)
        self.assertEqual(by_date[monday + dt.timedelta(days=3)], self.first.pk)

    def test_the_week_needs_at_least_one_cycle(self):
        response = self.client.post(
            reverse("console-schedule-week"),
            {"hall": self.hall.pk, "start": self.start.isoformat(), "cycles": []},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(MenuSchedule.objects.count(), 0)


class DishConsoleTests(TestCase):
    """Adding, editing and deleting dishes from the console."""

    def setUp(self):
        self.admin = make_user("admin", User.Role.MESS_ADMIN)
        self.manager = make_user("manager", User.Role.MESS_MANAGER)
        self.client.force_login(self.admin)

    def test_the_catalogue_renders(self):
        response = self.client.get(reverse("console-dishes"))
        self.assertEqual(response.status_code, 200)

    def test_a_mess_manager_cannot_reach_the_catalogue(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("console-dishes"))
        self.assertEqual(response.status_code, 403)

    def test_a_dish_is_added(self):
        response = self.client.post(
            reverse("console-dish-create"),
            {
                "name": "Masala Dosa",
                "code": "DOSA",
                "category": "STAPLE",
                "serving_size_g": "150",
            },
        )
        self.assertEqual(response.status_code, 302)
        dish = Dish.objects.get(code="DOSA")
        self.assertEqual(dish.name, "Masala Dosa")
        self.assertEqual(dish.serving_size_g, 150)

    def test_a_code_that_is_taken_is_refused(self):
        make_dish(code="RICE_DISH")
        response = self.client.post(
            reverse("console-dish-create"),
            {"name": "Another", "code": "RICE_DISH", "category": "VEG", "serving_size_g": "200"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Dish.objects.filter(code="RICE_DISH").count(), 1)

    def test_a_dish_is_edited(self):
        dish = make_dish(code="RICE_DISH")
        response = self.client.post(
            reverse("console-dish-update", args=[dish.pk]),
            {
                "name": "Steamed Rice",
                "code": "RICE_DISH",
                "category": "STAPLE",
                "serving_size_g": "220",
            },
        )
        self.assertEqual(response.status_code, 302)
        dish.refresh_from_db()
        self.assertEqual(dish.serving_size_g, 220)

    def test_the_edit_form_shows_the_dish(self):
        dish = make_dish(code="RICE_DISH")
        response = self.client.get(reverse("console-dish-update", args=[dish.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Steamed Rice")

    def test_a_dish_that_was_never_cooked_is_deleted(self):
        dish = make_dish(code="RICE_DISH")
        response = self.client.post(reverse("console-dish-delete", args=[dish.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Dish.objects.filter(pk=dish.pk).exists())

    def test_a_dish_that_has_been_cooked_is_refused(self):
        hall = make_hall()
        dish = make_dish(code="RICE_DISH")
        menu = make_menu()
        add_dish_to_menu(menu, dish)
        service = make_service(hall, dt.date(2026, 11, 5))
        make_actual(service, dishes=[(dish, 100, 80)])

        response = self.client.post(reverse("console-dish-delete", args=[dish.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cannot be deleted")
        self.assertTrue(Dish.objects.filter(pk=dish.pk).exists())

    def test_a_dish_that_has_been_cooked_can_be_retired(self):
        hall = make_hall()
        dish = make_dish(code="RICE_DISH")
        menu = make_menu()
        add_dish_to_menu(menu, dish)
        service = make_service(hall, dt.date(2026, 11, 5))
        make_actual(service, dishes=[(dish, 100, 80)])

        response = self.client.post(
            reverse("console-dish-delete", args=[dish.pk]), {"action": "retire"}
        )
        self.assertEqual(response.status_code, 302)
        dish.refresh_from_db()
        self.assertFalse(dish.is_active)
        self.assertTrue(Dish.objects.filter(pk=dish.pk).exists())


class ProtectedDeleteTests(TestCase):
    """A delete the schema refuses must come back as a 409, not a 500."""

    def setUp(self):
        self.admin = make_user("admin", User.Role.MESS_ADMIN)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_deleting_a_dish_in_use_is_a_conflict(self):
        dish = make_dish(code="RICE_DISH")
        menu = make_menu()
        add_dish_to_menu(menu, dish)
        response = self.client.delete(f"/api/dishes/{dish.pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertIn("detail", response.data)
        self.assertIn("cannot be deleted", response.data["detail"])

    def test_deleting_a_dish_that_is_not_in_use_succeeds(self):
        dish = make_dish(code="RICE_DISH")
        response = self.client.delete(f"/api/dishes/{dish.pk}/")
        self.assertEqual(response.status_code, 204)

    def test_deleting_a_menu_that_is_scheduled_is_a_conflict(self):
        menu = make_menu()
        hall = make_hall()
        schedule_menu(menu, hall, dt.date(2026, 11, 9), "LUNCH")
        response = self.client.delete(f"/api/menus/{menu.pk}/")
        self.assertEqual(response.status_code, 409)


class MenuApiTests(TestCase):
    """The endpoints the specification names, and what each one does."""

    def setUp(self):
        self.manager = make_user("manager", User.Role.MESS_MANAGER)
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def test_the_collection_is_listed(self):
        response = self.client.get("/api/menus/")
        self.assertEqual(response.status_code, 200)

    def test_a_menu_is_created(self):
        response = self.client.post(
            "/api/menus/", {"name": "Menu Cycle A", "code": "MENU_A"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Menu.objects.filter(code="MENU_A").count(), 1)

    def test_a_menu_is_read(self):
        menu = make_menu()
        response = self.client.get(f"/api/menus/{menu.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["code"], menu.code)

    def test_a_menu_is_updated(self):
        menu = make_menu()
        response = self.client.put(
            f"/api/menus/{menu.pk}/",
            {"name": "Menu Cycle A revised", "code": menu.code},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        menu.refresh_from_db()
        self.assertEqual(menu.name, "Menu Cycle A revised")

    def test_a_menu_is_deleted(self):
        menu = make_menu()
        response = self.client.delete(f"/api/menus/{menu.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Menu.objects.filter(pk=menu.pk).exists())

    def test_a_mess_manager_cannot_delete_a_dish(self):
        dish = make_dish(code="RICE_DISH")
        response = self.client.delete(f"/api/dishes/{dish.pk}/")
        self.assertEqual(response.status_code, 403)


class CalendarConsoleTests(TestCase):
    """The calendar is edited from the console."""

    def setUp(self):
        self.manager = make_user("manager", User.Role.MESS_MANAGER)
        self.client.force_login(self.manager)

    def test_an_event_is_added(self):
        response = self.client.post(
            reverse("console-event-create"),
            {
                "name": "Final examinations",
                "event_type": "EXAM",
                "start_date": "2026-12-01",
                "end_date": "2026-12-12",
                "impact_factor": "1.20",
            },
        )
        self.assertEqual(response.status_code, 302)
        event = CalendarEvent.objects.get(name="Final examinations")
        self.assertEqual(event.event_type, "EXAM")
        self.assertEqual(event.impact_factor, Decimal("1.2"))

    def test_an_event_that_ends_before_it_starts_is_refused(self):
        response = self.client.post(
            reverse("console-event-create"),
            {
                "name": "Backwards",
                "event_type": "EXAM",
                "start_date": "2026-12-12",
                "end_date": "2026-12-01",
                "impact_factor": "1.20",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CalendarEvent.objects.filter(name="Backwards").count(), 0)

    def test_an_event_is_edited(self):
        event = CalendarEvent.objects.create(
            name="Examinations",
            event_type="EXAM",
            start_date=dt.date(2026, 12, 1),
            end_date=dt.date(2026, 12, 12),
            impact_factor=1.2,
        )
        response = self.client.post(
            reverse("console-event-update", args=[event.pk]),
            {
                "name": "Final examinations",
                "event_type": "EXAM",
                "start_date": "2026-12-01",
                "end_date": "2026-12-20",
                "impact_factor": "1.30",
            },
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.name, "Final examinations")
        self.assertEqual(event.impact_factor, Decimal("1.3"))

    def test_an_event_is_deleted(self):
        event = CalendarEvent.objects.create(
            name="A festival",
            event_type="FEST",
            start_date=dt.date(2026, 12, 1),
            end_date=dt.date(2026, 12, 2),
            impact_factor=1.1,
        )
        response = self.client.post(reverse("console-event-delete", args=[event.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CalendarEvent.objects.filter(pk=event.pk).exists())

    def test_the_event_form_is_on_the_settings_screen(self):
        response = self.client.get(reverse("console-settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Effect on demand")


class ScheduleBoardMealTests(TestCase):
    """The board shows the meals the kitchen actually runs."""

    def setUp(self):
        from apps.menu import services as menu_services

        self.services = menu_services
        self.hall = make_hall()
        self.menu = make_menu()

    def test_a_mess_that_does_not_run_snacks_does_not_see_the_row(self):
        board = self.services.schedule_board(dt.date(2026, 11, 9), self.hall)
        codes = [m["code"] for m in board["meals"]]
        self.assertNotIn(MealType.SNACK.value, codes)
        self.assertIn(MealType.LUNCH.value, codes)

    def test_a_mess_that_runs_snacks_sees_the_row(self):
        schedule_menu(self.menu, self.hall, dt.date(2026, 11, 10), MealType.SNACK.value)
        board = self.services.schedule_board(dt.date(2026, 11, 9), self.hall)
        codes = [m["code"] for m in board["meals"]]
        self.assertIn(MealType.SNACK.value, codes)
