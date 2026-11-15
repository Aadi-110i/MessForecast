"""M8 — waste measurement and costing.

The specification requires: "waste cost arithmetic verified against a manual
calculation for a full week".

The manual calculation here is written out longhand from the recipe and the
price list, with no reference to the application's own helper functions, so
the two genuinely agree by calculation rather than by construction.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.test import TestCase

from apps.waste.models import WasteRecord
from apps.waste.services import (
    average_waste_cost_per_service,
    compute_waste_for_actual,
    top_waste_dishes,
    waste_by_meal,
    waste_totals,
)

from .factories import (
    make_actual,
    make_dish,
    make_hall,
    make_ingredient,
    make_recipe,
    make_service,
)


class WasteCostArithmeticTests(TestCase):
    def setUp(self):
        self.hall = make_hall()
        self.rice = make_ingredient("RICE", "Rice", "kg", "45")
        self.ghee = make_ingredient("GHEE", "Ghee", "kg", "620")
        self.salt = make_ingredient("SALT", "Salt", "kg", "18")
        self.dish = make_dish("RICE_DISH", "Steamed Rice", serving="200")
        # 200 g of rice, 5 g of ghee, 2 g of salt per portion.
        self.recipe = make_recipe(
            self.dish,
            [
                (self.rice, "0.180", "0"),
                (self.ghee, "0.005", "0"),
                (self.salt, "0.002", "0"),
            ],
        )

    def test_the_cost_of_one_portion_is_the_recipe_times_the_prices(self):
        # Hand calculation:
        #   rice  0.180 kg x Rs 45.00 = Rs  8.1000
        #   ghee  0.005 kg x Rs 620.00 = Rs 3.1000
        #   salt  0.002 kg x Rs 18.00 = Rs  0.0360
        #   ------------------------------------------
        #   cost per portion               Rs 11.2360
        self.assertEqual(self.dish.cost_per_portion(dt.date(2026, 11, 5)), Decimal("11.2360"))

    def test_waste_cost_for_one_service(self):
        service = make_service(self.hall, dt.date(2026, 11, 5), attendance=500)
        actual = make_actual(
            service, prepared=600, served=540, dishes=[(self.dish, 600, 540)]
        )

        compute_waste_for_actual(actual)

        record = WasteRecord.objects.get(service_actual=actual, dish=self.dish)
        # 60 portions left over x Rs 11.2360 = Rs 674.16
        self.assertEqual(record.leftover_portions, 60)
        self.assertEqual(record.waste_cost, Decimal("674.16"))
        # 60 portions x 200 g = 12 kg
        self.assertEqual(record.waste_quantity, Decimal("12.000"))

    def test_a_full_week_reconciles_with_a_manual_calculation(self):
        """Seven services, hand-totalled, must equal the platform's total."""
        week_start = dt.date(2026, 11, 2)
        expected_total = Decimal("0")
        expected_kg = Decimal("0")
        leftovers = [40, 55, 30, 62, 18, 47, 25]

        for index, leftover in enumerate(leftovers):
            service = make_service(
                self.hall, week_start + dt.timedelta(days=index), attendance=500
            )
            actual = make_actual(
                service,
                prepared=600,
                served=600 - leftover,
                dishes=[(self.dish, 600, 600 - leftover)],
            )
            compute_waste_for_actual(actual)

            # Manual arithmetic, written out for this service:
            #   40 x (0.180 x 45 + 0.005 x 620 + 0.002 x 18) = 40 x 11.2360
            manual = Decimal(leftover) * Decimal("11.2360")
            expected_total += manual
            expected_kg += Decimal(leftover) * Decimal("200") / Decimal("1000")

        totals = waste_totals(week_start, week_start + dt.timedelta(days=6))

        self.assertEqual(totals["waste_cost"], expected_total.quantize(Decimal("0.01")))
        self.assertEqual(totals["waste_quantity_kg"], expected_kg.quantize(Decimal("0.001")))
        self.assertEqual(totals["records"], 7)

        # And the per-service average must reconcile too.
        average = average_waste_cost_per_service(week_start, week_start + dt.timedelta(days=6))
        self.assertEqual(
            average,
            (expected_total / Decimal("7")).quantize(Decimal("0.01")),
        )

    def test_trim_loss_is_included_in_the_cost(self):
        """Potatoes: 100 g net per portion, 20% peel loss, Rs 28 a kilo."""
        potato = make_ingredient("POTATO", "Potatoes", "kg", "28")
        dish = make_dish("ALOO", "Aloo", serving="150")
        make_recipe(dish, [(potato, "0.100", "20")])

        # 0.100 x 1.20 = 0.120 kg bought x Rs 28 = Rs 3.36 per portion
        self.assertEqual(dish.cost_per_portion(dt.date(2026, 11, 5)), Decimal("3.3600"))

    def test_a_dish_with_no_recipe_costs_nothing(self):
        dish = make_dish("FREE", "Free Item", serving="100")
        self.assertEqual(dish.cost_per_portion(dt.date(2026, 11, 5)), Decimal("0"))

    def test_recomputing_waste_is_idempotent(self):
        service = make_service(self.hall, dt.date(2026, 11, 5), attendance=500)
        actual = make_actual(service, prepared=600, served=540, dishes=[(self.dish, 600, 540)])

        compute_waste_for_actual(actual)
        compute_waste_for_actual(actual)

        self.assertEqual(WasteRecord.objects.count(), 1)
        self.assertEqual(WasteRecord.objects.get().waste_cost, Decimal("674.16"))


class WasteReportingTests(TestCase):
    def setUp(self):
        self.hall = make_hall()
        self.other = make_hall("SOUTH", "South Block Mess")
        self.dish_a = make_dish("A", "Dish A")
        self.dish_b = make_dish("B", "Dish B")
        self.ingredient = make_ingredient("RICE", "Rice", "kg", "45")
        make_recipe(self.dish_a, [(self.ingredient, "0.180", "0")])
        make_recipe(self.dish_b, [(self.ingredient, "0.100", "0")])

        self.day = dt.date(2026, 11, 5)
        service_a = make_service(self.hall, self.day, attendance=500)
        actual_a = make_actual(
            service_a, prepared=600, served=500,
            dishes=[(self.dish_a, 600, 500), (self.dish_b, 200, 200)],
        )
        compute_waste_for_actual(actual_a)

        service_b = make_service(self.other, self.day, attendance=300)
        actual_b = make_actual(
            service_b, prepared=400, served=380,
            dishes=[(self.dish_a, 400, 380)],
        )
        compute_waste_for_actual(actual_b)

    def test_top_waste_dishes_are_ranked_by_cost(self):
        rows = top_waste_dishes(self.day, self.day, limit=5)
        self.assertEqual(rows[0]["dish"], "Dish A")
        self.assertGreater(rows[0]["waste_cost"], rows[1]["waste_cost"])

    def test_totals_can_be_scoped_to_one_hall(self):
        all_halls = waste_totals(self.day, self.day)
        one_hall = waste_totals(self.day, self.day, self.other)

        self.assertGreater(all_halls["waste_cost"], one_hall["waste_cost"])
        self.assertEqual(one_hall["records"], 1)

    def test_waste_by_meal_is_reported(self):
        rows = waste_by_meal(self.day, self.day)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["meal"], "LUNCH")
        self.assertGreater(rows[0]["waste_cost"], 0)
