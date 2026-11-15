"""M5 — the forecasting engine.

The specification requires "forecast reproducibility" to be tested. The engine
contains no randomness and no wall-clock dependence, so the same history must
always produce the same numbers and the same input signature.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.test import TestCase

from apps.forecasting.engine import BaselineForecaster, Observation
from apps.forecasting.services import build_history, forecast_service
from apps.forecasting.models import Forecast

from .factories import make_hall, make_service


def build_observations(start=dt.date(2026, 9, 1), weeks=8, base=500):
    """A tidy history: a weekday rhythm with a little noise."""
    observations = []
    current = start
    for index in range(weeks * 7):
        weekday_factor = {0: 0.92, 1: 0.94, 2: 0.95, 3: 0.97, 4: 1.08, 5: 1.12, 6: 1.05}[
            current.weekday()
        ]
        value = int(base * weekday_factor + (index % 5) * 2 - 4)
        observations.append(
            Observation(date=current, attendance=value, event_factor=Decimal("1"))
        )
        current += dt.timedelta(days=1)
    return observations


class ReproducibilityTests(TestCase):
    def test_same_history_gives_the_same_forecast(self):
        forecaster = BaselineForecaster()
        observations = build_observations()
        target = observations[-1].date + dt.timedelta(days=1)

        first = forecaster.predict(observations, target)
        second = forecaster.predict(observations, target)

        self.assertEqual(first.point_estimate, second.point_estimate)
        self.assertEqual(first.lower_bound, second.lower_bound)
        self.assertEqual(first.upper_bound, second.upper_bound)
        self.assertEqual(first.input_signature, second.input_signature)
        self.assertEqual(first.explanation, second.explanation)

    def test_input_signature_changes_when_the_history_changes(self):
        forecaster = BaselineForecaster()
        observations = build_observations()
        target = observations[-1].date + dt.timedelta(days=1)

        original = forecaster.predict(observations, target)

        changed = list(observations)
        changed[-1] = Observation(
            date=changed[-1].date, attendance=changed[-1].attendance + 25,
            event_factor=Decimal("1"),
        )
        altered = forecaster.predict(changed, target)

        self.assertNotEqual(original.input_signature, altered.input_signature)
        self.assertNotEqual(original.point_estimate, altered.point_estimate)

    def test_a_fresh_forecaster_instance_reproduces_the_same_numbers(self):
        """Reproducible across processes, not just within one object."""
        observations = build_observations()
        target = observations[-1].date + dt.timedelta(days=1)

        first = BaselineForecaster().predict(observations, target)
        second = BaselineForecaster().predict(observations, target)

        self.assertEqual(first.point_estimate, second.point_estimate)
        self.assertEqual(first.input_signature, second.input_signature)


class DatabaseForecastTests(TestCase):
    def setUp(self):
        self.hall = make_hall()
        start = dt.date(2026, 9, 1)
        for index in range(8 * 7):
            current = start + dt.timedelta(days=index)
            weekday_factor = {0: 0.92, 1: 0.94, 2: 0.95, 3: 0.97, 4: 1.08, 5: 1.12, 6: 1.05}[
                current.weekday()
            ]
            make_service(
                self.hall,
                current,
                attendance=int(500 * weekday_factor),
            )

    def test_forecast_is_stored_and_scored_against_the_actual(self):
        target = dt.date(2026, 10, 27)
        service = make_service(self.hall, target, attendance=540)

        result = forecast_service(service)

        forecast = Forecast.objects.get(service=service)
        self.assertEqual(forecast.service, service)
        self.assertTrue(forecast.predicted_attendance > 0)
        self.assertLessEqual(forecast.lower_bound, forecast.predicted_attendance)
        self.assertGreaterEqual(forecast.upper_bound, forecast.predicted_attendance)
        self.assertTrue(forecast.explanation)
        self.assertIn("expect about", forecast.explanation)
        self.assertEqual(result.input_signature, forecast.input_signature)

    def test_regenerating_the_forecast_gives_the_same_signature(self):
        target = dt.date(2026, 10, 27)
        service = make_service(self.hall, target, attendance=540)

        forecast_service(service)
        first = Forecast.objects.get(service=service).input_signature

        forecast_service(service)
        second = Forecast.objects.get(service=service).input_signature

        self.assertEqual(first, second)

    def test_history_is_built_from_the_recorded_attendance(self):
        target = dt.date(2026, 10, 27)
        history = build_history(self.hall, "LUNCH", target)
        self.assertEqual(len(history.observations), 8 * 7)
        self.assertTrue(all(o.attendance > 0 for o in history.observations))


class ColdStartTests(TestCase):
    def test_few_history_points_falls_back_and_says_so(self):
        forecaster = BaselineForecaster(min_history=6)
        observations = build_observations()[:3]

        result = forecaster.predict(
            observations,
            observations[-1].date + dt.timedelta(days=1),
            registered_strength=600,
        )

        self.assertTrue(result.fallback_used)
        self.assertIn("enough history", result.explanation.lower())
        # The fallback still gives the kitchen a number to work with.
        self.assertGreater(result.point_estimate, 0)
        self.assertLessEqual(result.lower_bound, result.point_estimate)
        self.assertGreaterEqual(result.upper_bound, result.point_estimate)


class EventAdjustmentTests(TestCase):
    def test_an_event_multiplies_the_estimate(self):
        forecaster = BaselineForecaster()
        observations = build_observations()
        target = observations[-1].date + dt.timedelta(days=1)

        normal = forecaster.predict(observations, target, target_event_factor=Decimal("1"))
        festive = forecaster.predict(observations, target, target_event_factor=Decimal("1.25"))

        self.assertGreater(festive.point_estimate, normal.point_estimate)

    def test_a_vacation_multiplier_reduces_the_estimate(self):
        forecaster = BaselineForecaster()
        observations = build_observations()
        target = observations[-1].date + dt.timedelta(days=1)

        normal = forecaster.predict(observations, target, target_event_factor=Decimal("1"))
        quiet = forecaster.predict(observations, target, target_event_factor=Decimal("0.30"))

        self.assertLess(quiet.point_estimate, normal.point_estimate)


class ConfidenceIntervalTests(TestCase):
    def test_the_interval_contains_the_point_estimate(self):
        forecaster = BaselineForecaster(confidence=0.80)
        observations = build_observations()
        target = observations[-1].date + dt.timedelta(days=1)

        result = forecaster.predict(observations, target)

        self.assertLessEqual(result.lower_bound, result.point_estimate)
        self.assertGreaterEqual(result.upper_bound, result.point_estimate)
        self.assertEqual(result.confidence_level, 0.80)

    def test_a_wider_confidence_level_gives_a_wider_interval(self):
        observations = build_observations()
        target = observations[-1].date + dt.timedelta(days=1)

        narrow = BaselineForecaster(confidence=0.50).predict(observations, target)
        wide = BaselineForecaster(confidence=0.95).predict(observations, target)

        self.assertGreater(
            wide.upper_bound - wide.lower_bound, narrow.upper_bound - narrow.lower_bound
        )

    def test_the_lower_bound_never_goes_negative(self):
        forecaster = BaselineForecaster()
        observations = build_observations()
        target = observations[-1].date + dt.timedelta(days=1)

        result = forecaster.predict(
            observations, target, target_event_factor=Decimal("0.10")
        )
        self.assertGreaterEqual(result.lower_bound, 0)
