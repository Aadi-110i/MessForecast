"""M6 — preparation planning and the ingredient indent."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.test import TestCase

from apps.forecasting.models import Forecast
from apps.planning.models import IngredientIndent, PreparationLine, PreparationPlan
from apps.planning.services import (
    PlanningError,
    format_indent,
    generate_preparation_plan,
    indent_csv_rows,
)
from apps.events.models import ServiceLevelConfig

from .factories import (
    add_dish_to_menu,
    make_dish,
    make_hall,
    make_ingredient,
    make_menu,
    make_recipe,
    make_service,
    schedule_menu,
)


class PreparationPlanTests(TestCase):
    def setUp(self):
        self.hall = make_hall()
        self.on_date = dt.date(2026, 11, 5)
        self.service = make_service(self.hall, self.on_date, attendance=0)

        self.rice = make_ingredient("RICE", "Rice", "kg", "45")
        self.dal = make_ingredient("DAL", "Toor Dal", "kg", "135")
        self.dish_rice = make_dish("RICE_DISH", "Steamed Rice", serving="200")
        self.dish_dal = make_dish("DAL", "Dal", serving="200")
        make_recipe(self.dish_rice, [(self.rice, "0.180", "0")])
        make_recipe(self.dish_dal, [(self.dal, "0.070", "0")])

        self.menu = make_menu()
        add_dish_to_menu(self.menu, self.dish_rice, meal="LUNCH", share="0.60", sequence=0)
        add_dish_to_menu(self.menu, self.dish_dal, meal="LUNCH", share="0.40", sequence=1)
        schedule_menu(self.menu, self.hall, self.on_date, meal="LUNCH")

        ServiceLevelConfig.objects.create(
            hall=None,
            meal="LUNCH",
            effective_from=dt.date(2026, 1, 1),
            acceptable_overprep_pct=Decimal("10.00"),
            max_overprep_pct=Decimal("18.00"),
            min_buffer_portions=0,
            portions_per_student=Decimal("2.00"),
        )

        self.forecast = Forecast.objects.create(
            service=self.service,
            method="recency_weighted_ma_weekday_event_trend",
            model_version="baseline-v1",
            predicted_attendance=Decimal("500"),
            lower_bound=Decimal("460"),
            upper_bound=Decimal("540"),
            confidence_level=Decimal("0.800"),
            input_signature="a" * 64,
            explanation="test",
        )

    def test_portions_follow_the_service_level_margin(self):
        plan = generate_preparation_plan(self.service, forecast=self.forecast)

        # 500 students x 2.00 portions x 1.10 margin = 1100 portions.
        self.assertEqual(plan.portions_to_prepare, 1100)
        self.assertEqual(plan.attendance_target, Decimal("500"))
        self.assertEqual(plan.portions_target, Decimal("1000"))
        self.assertEqual(plan.safety_margin_pct, Decimal("10.00"))

    def test_the_ceiling_is_respected(self):
        ServiceLevelConfig.objects.update(
            acceptable_overprep_pct=Decimal("40.00"), max_overprep_pct=Decimal("18.00")
        )
        level = ServiceLevelConfig.resolve(self.hall, "LUNCH", self.on_date)

        plan = generate_preparation_plan(self.service, forecast=self.forecast, service_level=level)

        # 500 x 2.00 x 1.18 = 1180, the ceiling, not the 40% request.
        self.assertEqual(plan.portions_to_prepare, 1180)

    def test_the_dish_split_always_adds_back_to_the_total(self):
        plan = generate_preparation_plan(self.service, forecast=self.forecast)

        total = sum(line.portions for line in plan.lines.all())
        self.assertEqual(total, plan.portions_to_prepare)
        self.assertEqual(len(plan.lines.all()), 2)

    def test_dish_portions_follow_the_learned_share(self):
        plan = generate_preparation_plan(self.service, forecast=self.forecast)

        rice = plan.lines.get(dish=self.dish_rice)
        dal = plan.lines.get(dish=self.dish_dal)
        self.assertEqual(rice.portions + dal.portions, 1100)
        self.assertGreater(rice.portions, dal.portions)

    def test_the_indent_is_built_from_the_recipes(self):
        plan = generate_preparation_plan(self.service, forecast=self.forecast)

        indent = IngredientIndent.objects.get(plan=plan)
        rice_line = indent.lines.get(ingredient=self.rice)
        dal_line = indent.lines.get(ingredient=self.dal)

        # Rice: 660 portions x 0.180 kg = 118.8 kg at Rs 45 = Rs 5346.00
        self.assertEqual(rice_line.quantity, Decimal("118.800"))
        self.assertEqual(rice_line.estimated_cost, Decimal("5346.00"))
        # Dal: 440 portions x 0.070 kg = 30.8 kg at Rs 135 = Rs 4158.00
        self.assertEqual(dal_line.quantity, Decimal("30.800"))
        self.assertEqual(dal_line.estimated_cost, Decimal("4158.00"))
        self.assertEqual(indent.total_estimated_cost, Decimal("9504.00"))

    def test_the_indent_renders_in_the_procurement_format(self):
        plan = generate_preparation_plan(self.service, forecast=self.forecast)
        indent = IngredientIndent.objects.get(plan=plan)

        text = format_indent(indent)
        self.assertIn("INDENT", text)
        self.assertIn("Rice", text)
        self.assertIn("Toor Dal", text)
        self.assertIn("TOTAL", text)

    def test_the_csv_export_has_a_row_per_ingredient(self):
        plan = generate_preparation_plan(self.service, forecast=self.forecast)
        indent = IngredientIndent.objects.get(plan=plan)

        header, rows = indent_csv_rows(indent)
        self.assertEqual(len(rows), 2)
        self.assertIn("Ingredient", header)
        self.assertIn("Estimated Cost (Rs)", header)
        self.assertEqual(rows[0][1], "Rice")

    def test_a_plan_needs_a_forecast(self):
        service = make_service(self.hall, self.on_date + dt.timedelta(days=1), attendance=0)
        with self.assertRaises(PlanningError):
            generate_preparation_plan(service)

    def test_a_plan_needs_a_menu(self):
        service = make_service(self.hall, self.on_date + dt.timedelta(days=2), attendance=0)
        Forecast.objects.create(
            service=service,
            method="m", model_version="v",
            predicted_attendance=Decimal("100"),
            lower_bound=Decimal("90"), upper_bound=Decimal("110"),
            confidence_level=Decimal("0.8"), input_signature="b" * 64,
        )
        with self.assertRaises(PlanningError):
            generate_preparation_plan(service)

    def test_regenerating_a_plan_replaces_the_old_one(self):
        generate_preparation_plan(self.service, forecast=self.forecast)
        generate_preparation_plan(self.service, forecast=self.forecast)

        self.assertEqual(PreparationPlan.objects.count(), 1)
        self.assertEqual(PreparationLine.objects.count(), 2)
