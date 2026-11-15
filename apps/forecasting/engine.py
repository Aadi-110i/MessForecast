"""The baseline forecasting engine.

This module is deliberately free of Django and database imports: it takes
observations and returns a forecast. That keeps the arithmetic testable, and it
keeps the "upgrade path" honest - when a term of data justifies a learned
model (Prophet, gradient boosting), this module is replaced rather than
rewritten, because the call site already speaks in observations and results.

The method, in plain terms
---------------------------
1. *Strip the event effect.* Every past service is divided by the multiplier
   that the event calendar gave it, so a festival week no longer teaches the
   model that Fridays are busy.
2. *Moving average, weighted towards the recent past.* The base level is a
   recency-weighted mean of the event-adjusted history. This is the moving
   average.
3. *Weekday adjustment.* The target weekday's own history is compared with the
   base level to get a factor ("Sundays run at 0.8 of a normal day"). The
   factor is shrunk towards 1.0 when there is little evidence for it.
4. *Trend.* A damped least-squares slope carries a slow rise or fall forward,
   capped so a short history cannot produce a wild number.
5. *Event adjustment for the target date.* Overlapping calendar events
   multiply the result.
6. *Confidence interval.* A rolling walk-forward backtest over the same
   history measures how wrong this method has actually been, and the interval
   is sized from that measured error.

There is no randomness anywhere, so the same history always produces the same
forecast. ``input_signature`` records a hash of everything that was used, which
is what makes "forecast reproducibility" a testable property.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

METHOD_NAME = "recency_weighted_ma_weekday_event_trend"
MODEL_VERSION = "baseline-v1"

DEFAULT_DECAY = 0.85
"""Recency weight per week. 0.85 means a week-old observation counts 85% of the
weight of the most recent one, so a fortnight-old week counts about 72%."""

SHRINKAGE_K = 2.0
"""How much evidence is needed before a weekday factor is believed in full."""

MAX_TREND_PCT_PER_WEEK = Decimal("3.0")
MAX_TOTAL_TREND_PCT = Decimal("15.0")
MIN_HISTORY_FOR_MODEL = 6
DEFAULT_CONFIDENCE = 0.80
FALLBACK_RELATIVE_WIDTH_PCT = Decimal("25.0")
MIN_RELATIVE_WIDTH_PCT = Decimal("4.0")
MAX_EVENT_FACTOR = Decimal("3.0")
MIN_EVENT_FACTOR = Decimal("0.10")

WEEKDAY_LABELS = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
]


def _dec(value: Decimal | float | int, places: str = "0.01") -> Decimal:
    return Decimal(str(value)).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _z_for(confidence: float) -> float:
    """Two-sided z multiplier for a confidence level (default 0.80 -> 1.2816)."""
    p = 0.5 + confidence / 2.0
    p = min(max(p, 0.5), 0.9995)
    # Acklam's rational approximation of the inverse normal CDF.
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
                ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


@dataclass(frozen=True)
class Observation:
    """One historical service: how many people actually turned up."""

    date: dt.date
    attendance: int
    event_factor: Decimal = Decimal("1")
    is_exam_period: bool = False
    weekday: int = field(default=None, compare=False)  # type: ignore[assignment]

    def __post_init__(self):
        if self.weekday is None:
            object.__setattr__(self, "weekday", self.date.weekday())


@dataclass
class ForecastResult:
    """Everything the rest of the system needs to know about one forecast."""

    point_estimate: Decimal
    lower_bound: Decimal
    upper_bound: Decimal
    confidence_level: float
    base_level: Decimal
    weekday_factor: Decimal
    event_factor: Decimal
    trend_pct: Decimal
    rmse: Decimal
    mape: Decimal
    method: str
    model_version: str
    input_signature: str
    explanation: str
    observations_used: int
    fallback_used: bool = False

    def as_dict(self) -> dict:
        return {
            "point_estimate": self.point_estimate,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "confidence_level": self.confidence_level,
            "base_level": self.base_level,
            "weekday_factor": self.weekday_factor,
            "event_factor": self.event_factor,
            "trend_pct": self.trend_pct,
            "rmse": self.rmse,
            "mape": self.mape,
            "method": self.method,
            "model_version": self.model_version,
            "input_signature": self.input_signature,
            "observations_used": self.observations_used,
            "fallback_used": self.fallback_used,
        }


class InsufficientHistory(Exception):
    """Raised when there is not enough history to run the model at all."""


class BaselineForecaster:
    """Recency-weighted moving average with weekday, event and trend adjustment."""

    def __init__(
        self,
        decay: float = DEFAULT_DECAY,
        confidence: float = DEFAULT_CONFIDENCE,
        min_history: int = MIN_HISTORY_FOR_MODEL,
        shrinkage_k: float = SHRINKAGE_K,
    ):
        self.decay = decay
        self.confidence = confidence
        self.min_history = min_history
        self.shrinkage_k = shrinkage_k

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _clean(self, obs: Observation) -> float:
        """Attendance with the event effect removed."""
        factor = float(obs.event_factor) if obs.event_factor and obs.event_factor > 0 else 1.0
        return obs.attendance / factor

    def _weighted_base(self, obs: list[Observation]) -> Decimal:
        """Recency-weighted mean of the event-adjusted history.

        The arithmetic runs in floating point on purpose. The weight is
        ``decay ** weeks_ago``, and a Decimal raised to a fractional power is
        an order of magnitude slower than ``math.pow`` — and the walk-forward
        backtest evaluates this function thousands of times per forecast.
        Decimal is used for the result, which is what the rest of the system
        and the money arithmetic depend on.
        """
        last_date = obs[-1].date
        weighted_sum = 0.0
        weight_total = 0.0
        for o in obs:
            weeks_ago = (last_date - o.date).days / 7.0
            weight = self.decay ** weeks_ago
            weighted_sum += weight * self._clean(o)
            weight_total += weight
        if weight_total == 0:
            return Decimal("0")
        return _dec(weighted_sum / weight_total)

    def _weekday_factor(self, obs: list[Observation], base: Decimal, target_weekday: int) -> tuple[Decimal, int]:
        same_weekday = [o for o in obs if o.date.weekday() == target_weekday]
        n = len(same_weekday)
        if n == 0 or base == 0:
            return Decimal("1"), 0
        mean_same = sum(self._clean(o) for o in same_weekday) / n
        raw = mean_same / float(base)
        # Shrink towards 1.0: a factor built from two observations is not as
        # trustworthy as one built from twenty.
        shrink = n / (n + self.shrinkage_k)
        return _dec(1.0 + (raw - 1.0) * shrink, "0.0001"), n

    def _trend(self, obs: list[Observation], base: Decimal, target_date: dt.date) -> Decimal:
        if len(obs) < 3 or base == 0:
            return Decimal("0")
        last_date = obs[-1].date
        xs = [(last_date - o.date).days / 7.0 for o in obs]
        ys = [self._clean(o) for o in obs]
        n = float(len(obs))
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        denom = sum((x - mean_x) ** 2 for x in xs)
        if denom == 0:
            return Decimal("0")
        slope = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(len(xs))) / denom
        per_week = slope / float(base)
        max_per_week = float(MAX_TREND_PCT_PER_WEEK) / 100.0
        per_week = max(min(per_week, max_per_week), -max_per_week)
        weeks_ahead = (target_date - last_date).days / 7.0
        total = per_week * weeks_ahead
        max_total = float(MAX_TOTAL_TREND_PCT) / 100.0
        return _dec(max(min(total, max_total), -max_total), "0.0001")

    def _point_estimate(
        self,
        obs: list[Observation],
        target_date: dt.date,
        target_event_factor: Decimal,
    ) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        base = self._weighted_base(obs)
        weekday_factor, _ = self._weekday_factor(obs, base, target_date.weekday())
        trend = self._trend(obs, base, target_date)
        point = base * weekday_factor * (Decimal("1") + trend) * target_event_factor
        if point < 0:
            point = Decimal("0")
        return point, base, weekday_factor, trend

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def backtest(self, observations: list[Observation]) -> tuple[Decimal, Decimal, int]:
        """Walk forward through the history and measure how wrong we were.

        Returns ``(rmse, mape, samples)``. The RMSE drives the confidence
        interval; the MAPE is the honest accuracy figure reported to the mess
        manager.
        """
        obs = sorted(observations, key=lambda o: o.date)
        abs_errors: list[Decimal] = []
        pct_errors: list[Decimal] = []
        for k in range(self.min_history, len(obs)):
            train = obs[:k]
            target = obs[k]
            if target.attendance <= 0:
                continue
            point, _, _, _ = self._point_estimate(train, target.date, target.event_factor)
            error = abs(Decimal(target.attendance) - point)
            abs_errors.append(error)
            pct_errors.append(error / Decimal(target.attendance) * Decimal("100"))
        if not abs_errors:
            return Decimal("0"), Decimal("0"), 0
        rmse = (sum((e * e for e in abs_errors), Decimal("0")) / Decimal(len(abs_errors))) ** Decimal("0.5")
        mape = sum(pct_errors, Decimal("0")) / Decimal(len(pct_errors))
        return _dec(rmse), _dec(mape), len(abs_errors)

    def predict(
        self,
        observations: list[Observation],
        target_date: dt.date,
        target_event_factor: Decimal = Decimal("1"),
        registered_strength: int = 0,
        fallback_attendance_rate: Decimal | None = None,
        context: dict | None = None,
    ) -> ForecastResult:
        """Produce the forecast for ``target_date``."""
        context = context or {}
        obs = sorted(
            [o for o in observations if o.date < target_date], key=lambda o: o.date
        )

        event_factor = target_event_factor if target_event_factor and target_event_factor > 0 else Decimal("1")
        event_factor = max(min(event_factor, MAX_EVENT_FACTOR), MIN_EVENT_FACTOR)

        if len(obs) < self.min_history:
            return self._fallback(
                obs, target_date, event_factor, registered_strength, fallback_attendance_rate, context
            )

        point, base, weekday_factor, trend = self._point_estimate(obs, target_date, event_factor)
        rmse, mape, samples = self.backtest(obs)

        z = _z_for(self.confidence)
        half_width = Decimal(str(z)) * rmse
        # Never hand back an implausibly tight interval.
        min_half = point * Decimal(str(MIN_RELATIVE_WIDTH_PCT)) / Decimal("100")
        if half_width < min_half:
            half_width = min_half
        lower = max(Decimal("0"), point - half_width)
        upper = point + half_width

        signature = self._signature(obs, target_date, event_factor)
        explanation = self._explain(
            obs=obs,
            target_date=target_date,
            point=point,
            base=base,
            weekday_factor=weekday_factor,
            trend=trend,
            event_factor=event_factor,
            rmse=rmse,
            mape=mape,
            lower=lower,
            upper=upper,
            context=context,
        )

        return ForecastResult(
            point_estimate=_dec(point),
            lower_bound=_dec(lower),
            upper_bound=_dec(upper),
            confidence_level=self.confidence,
            base_level=_dec(base),
            weekday_factor=_dec(weekday_factor, "0.0001"),
            event_factor=_dec(event_factor, "0.0001"),
            trend_pct=_dec(trend * 100),
            rmse=_dec(rmse),
            mape=_dec(mape),
            method=METHOD_NAME,
            model_version=MODEL_VERSION,
            input_signature=signature,
            explanation=explanation,
            observations_used=len(obs),
            fallback_used=False,
        )

    # ------------------------------------------------------------------
    def _fallback(
        self,
        obs: list[Observation],
        target_date: dt.date,
        event_factor: Decimal,
        registered_strength: int,
        fallback_attendance_rate: Decimal | None,
        context: dict,
    ) -> ForecastResult:
        """Cold start: not enough history for the model.

        Fall back to the registered strength scaled by the best attendance rate
        we can find, with a deliberately wide interval.
        """
        rate = fallback_attendance_rate
        basis = "registered strength"
        if rate is None and obs:
            rate = Decimal(sum(o.attendance for o in obs)) / Decimal(len(obs) * max(registered_strength, 1))
            rate = min(rate, Decimal("1"))
            basis = "recent observed attendance"
        if rate is None:
            rate = Decimal("0.75")
            basis = "a default campus attendance assumption"
        base = Decimal(registered_strength or 0) * rate
        point = base * event_factor
        width = point * Decimal(str(FALLBACK_RELATIVE_WIDTH_PCT)) / Decimal("100")
        lower = max(Decimal("0"), point - width)
        upper = point + width
        signature = self._signature(obs, target_date, event_factor)
        explanation = (
            f"We do not have enough history yet to forecast this service reliably "
            f"(only {len(obs)} past services recorded, we need {self.min_history}). "
            f"As a starting point we have used {basis} of {registered_strength} registered "
            f"students, giving about {int(point)} portions. Plan with a wide margin "
            f"between {int(lower)} and {int(upper)} until more data is collected."
        )
        return ForecastResult(
            point_estimate=_dec(point),
            lower_bound=_dec(lower),
            upper_bound=_dec(upper),
            confidence_level=self.confidence,
            base_level=_dec(base),
            weekday_factor=Decimal("1"),
            event_factor=_dec(event_factor, "0.0001"),
            trend_pct=Decimal("0"),
            rmse=Decimal("0"),
            mape=Decimal("0"),
            method=METHOD_NAME,
            model_version=MODEL_VERSION,
            input_signature=signature,
            explanation=explanation,
            observations_used=len(obs),
            fallback_used=True,
        )

    def _signature(self, obs: list[Observation], target_date: dt.date, event_factor: Decimal) -> str:
        """Hash of everything that fed the forecast, for reproducibility checks."""
        parts = [
            METHOD_NAME,
            MODEL_VERSION,
            target_date.isoformat(),
            f"decay={self.decay}",
            f"k={self.shrinkage_k}",
            f"conf={self.confidence}",
            f"event={event_factor}",
        ]
        parts.extend(f"{o.date.isoformat()}:{o.attendance}:{o.event_factor}" for o in obs)
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    def _explain(
        self,
        obs: list[Observation],
        target_date: dt.date,
        point: Decimal,
        base: Decimal,
        weekday_factor: Decimal,
        trend: Decimal,
        event_factor: Decimal,
        rmse: Decimal,
        mape: Decimal,
        lower: Decimal,
        upper: Decimal,
        context: dict,
    ) -> str:
        """Write the forecast out in language a mess manager can act on."""
        hall = context.get("hall_name") or "this hall"
        meal = context.get("meal_label") or "this meal"
        weekday = WEEKDAY_LABELS[target_date.weekday()]
        weeks = len({(target_date - o.date).days // 7 for o in obs})
        span = f"the last {max(weeks, 1)} week" + ("s" if max(weeks, 1) > 1 else "")

        lines = [
            f"{meal} at {hall} on {weekday} {target_date.strftime('%d %b %Y')}: "
            f"we expect about {int(round(point))} students.",
            f"Working: over {span} this service has been running at roughly "
            f"{int(round(base))} students once festivals and exam weeks are removed.",
        ]

        if abs(weekday_factor - 1) >= Decimal("0.02"):
            direction = "busier" if weekday_factor > 1 else "quieter"
            lines.append(
                f"{weekday}s specifically run {abs(weekday_factor - 1) * 100:.0f}% {direction} "
                f"than that average, so the weekday has been taken into account."
            )
        else:
            lines.append(f"{weekday}s behave like an average day, so no weekday adjustment was needed.")

        if abs(trend) >= Decimal("0.01"):
            direction = "rising" if trend > 0 else "falling"
            lines.append(f"Attendance has been slowly {direction}, so a small {abs(trend) * 100:.0f}% adjustment was applied.")

        if abs(event_factor - 1) >= Decimal("0.01"):
            if event_factor > 1:
                lines.append(
                    f"{context.get('event_names') or 'An event on the calendar'} is expected to pull "
                    f"attendance up by {(event_factor - 1) * 100:.0f}%."
                )
            else:
                lines.append(
                    f"{context.get('event_names') or 'An event on the calendar'} is expected to pull "
                    f"attendance down by {(1 - event_factor) * 100:.0f}%."
                )

        if rmse > 0:
            lines.append(
                f"Uncertainty: our forecasts for this hall have been out by about {int(round(rmse))} "
                f"portions on a typical day recently (average error {mape:.1f}%), so a sensible "
                f"planning range is {int(round(lower))} to {int(round(upper))} portions."
            )
        else:
            lines.append(
                f"We have limited error history for this hall yet, so plan between "
                f"{int(round(lower))} and {int(round(upper))} portions."
            )
        return " ".join(lines)
