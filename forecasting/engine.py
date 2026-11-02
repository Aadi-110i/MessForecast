"""
Forecasting engine: Weighted Moving Average baseline with weekday + event adjustments.

Plain-language explanation for mess managers:
----------------------------------------------
We look at the last 28 days of actual attendance for this meal service and dining hall.
We give more weight to recent meals (50%) and same-weekday meals (30%), with 20% for
event adjustments. If today is a holiday or exam period, we apply the configured multiplier.
The confidence range (±X) shows the typical variation we expect.

We do NOT use machine learning yet. That only makes sense after 6–12 months of data.
"""
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import pandas as pd
import numpy as np

from django.db import models as django_models
from django.utils import timezone

logger = logging.getLogger(__name__)


def _get_attendance_history(meal_service_id: int, dining_hall_id: int, 
                              lookback_days: int = 28) -> pd.DataFrame:
    """Fetch attendance summary history as DataFrame."""
    from attendance.models import AttendanceSummary
    
    cutoff = date.today() - timedelta(days=lookback_days)
    qs = AttendanceSummary.objects.filter(
        meal_service_id=meal_service_id,
        dining_hall_id=dining_hall_id,
        date__gte=cutoff,
        finalized=True,
        valid_count__gt=0,
    ).values('date', 'valid_count', 'day_of_week', 'is_holiday', 
             'is_exam_period', 'is_event_day')
    
    if not qs.exists():
        return pd.DataFrame()
    
    df = pd.DataFrame(list(qs))
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    return df


def _get_event_multiplier_for_date(target_date: date, 
                                    dining_hall_id: int,
                                    meal_service) -> float:
    """Get the attendance multiplier from calendar events for a given date."""
    from calendar_events.models import CalendarEvent
    from core.models import MealService
    
    events = CalendarEvent.objects.filter(
        start_date__lte=target_date,
        end_date__gte=target_date,
    ).filter(
        django_models.Q(affected_halls__isnull=True) |
        django_models.Q(affected_halls=dining_hall_id)
    )
    
    if not events.exists():
        return 1.0
    
    # Take the most impactful event
    multipliers = [float(e.attendance_multiplier) for e in events]
    return min(multipliers)  # Conservative: take the lowest (most impactful reduction)


def generate_forecast(
    meal_service_id: int,
    dining_hall_id: int,
    target_date: date,
    forecast_model_config=None,
) -> dict:
    """
    Core forecasting function. Returns a dict with:
        predicted_attendance, lower_bound, upper_bound,
        weekday, is_holiday, is_exam_period, event_multiplier,
        historical_avg, same_weekday_avg, data_points_used
    
    Method: Weighted Moving Average
    --------------------------------
    1. Gather last N days of finalized attendance.
    2. Compute:
       a. simple_avg = mean of all records
       b. weekday_avg = mean of same-weekday records
       c. recent_avg = mean of last 7 days
    3. Blended estimate = recency_weight*recent_avg + weekday_weight*weekday_avg 
                         + (1 - recency_weight - weekday_weight)*simple_avg
    4. Apply event multiplier from calendar.
    5. Confidence range = ±1 std deviation of historical data.
    """
    from core.models import MealService, DiningHall
    from calendar_events.models import CalendarEvent
    from forecasting.models import ForecastModel
    
    # Load config
    if forecast_model_config is None:
        try:
            forecast_model_config = ForecastModel.objects.filter(is_active=True).first()
        except Exception:
            forecast_model_config = None
    
    lookback_days = getattr(forecast_model_config, 'lookback_days', 28)
    weekday_weight = float(getattr(forecast_model_config, 'weekday_weight', 0.30))
    recency_weight = float(getattr(forecast_model_config, 'recency_weight', 0.50))
    # remainder goes to simple average
    
    df = _get_attendance_history(meal_service_id, dining_hall_id, lookback_days)
    
    target_weekday = target_date.weekday()  # 0=Monday
    
    # Check calendar events
    try:
        meal_service = MealService.objects.get(pk=meal_service_id)
        dining_hall = DiningHall.objects.get(pk=dining_hall_id)
    except Exception:
        logger.error("Invalid meal_service_id or dining_hall_id")
        return None
    
    event_multiplier = _get_event_multiplier_for_date(
        target_date, dining_hall_id, meal_service
    )
    
    # Check if it's a holiday or exam
    events_on_date = CalendarEvent.objects.filter(
        start_date__lte=target_date,
        end_date__gte=target_date,
    )
    is_holiday = events_on_date.filter(event_type='holiday').exists()
    is_exam = events_on_date.filter(event_type='exam').exists()
    
    if df.empty:
        # No history: use registered strength as fallback
        logger.warning(f"No history for ms={meal_service_id}, dh={dining_hall_id}. Using registered strength.")
        base = dining_hall.registered_strength or 500
        predicted = int(base * 0.7 * event_multiplier)  # assume 70% show rate
        return {
            'predicted_attendance': predicted,
            'lower_bound': int(predicted * 0.8),
            'upper_bound': int(predicted * 1.2),
            'weekday': target_weekday,
            'is_holiday': is_holiday,
            'is_exam_period': is_exam,
            'event_multiplier': Decimal(str(round(event_multiplier, 2))),
            'historical_avg': None,
            'same_weekday_avg': None,
            'data_points_used': 0,
        }
    
    counts = df['valid_count'].values.astype(float)
    
    # a. Simple average
    simple_avg = counts.mean()
    
    # b. Same-weekday average
    same_day_df = df[df['day_of_week'] == target_weekday]
    weekday_avg = same_day_df['valid_count'].mean() if not same_day_df.empty else simple_avg
    
    # c. Recent average (last 7 days)
    recent_df = df.tail(7)
    recent_avg = recent_df['valid_count'].mean() if not recent_df.empty else simple_avg
    
    # Blended estimate
    remaining_weight = 1.0 - recency_weight - weekday_weight
    blended = (
        recency_weight * recent_avg +
        weekday_weight * weekday_avg +
        remaining_weight * simple_avg
    )
    
    # Apply event multiplier
    predicted = blended * event_multiplier
    
    # Confidence interval: ±1 std dev (covers ~68%), expand to ~80% CI
    std = counts.std() if len(counts) > 1 else blended * 0.10
    ci_factor = 1.28  # 80% CI = ±1.28 std
    lower = max(0, int(predicted - ci_factor * std))
    upper = int(predicted + ci_factor * std)
    
    return {
        'predicted_attendance': max(0, int(round(predicted))),
        'lower_bound': lower,
        'upper_bound': upper,
        'weekday': target_weekday,
        'is_holiday': is_holiday,
        'is_exam_period': is_exam,
        'event_multiplier': Decimal(str(round(event_multiplier, 2))),
        'historical_avg': Decimal(str(round(simple_avg, 2))),
        'same_weekday_avg': Decimal(str(round(weekday_avg, 2))),
        'data_points_used': len(df),
    }


def generate_7day_forecast(meal_service_id: int, dining_hall_id: int,
                             forecast_model=None) -> list:
    """Generate 7-day rolling forecast starting from tomorrow."""
    forecasts = []
    tomorrow = date.today() + timedelta(days=1)
    
    for i in range(7):
        target = tomorrow + timedelta(days=i)
        result = generate_forecast(meal_service_id, dining_hall_id, target, forecast_model)
        if result:
            result['date'] = target
            result['meal_service_id'] = meal_service_id
            result['dining_hall_id'] = dining_hall_id
            forecasts.append(result)
    
    return forecasts


def save_forecast(meal_service_id: int, dining_hall_id: int, 
                   target_date: date, generated_by: str = 'system') -> Optional[object]:
    """Generate and save a Forecast record."""
    from forecasting.models import Forecast, ForecastModel
    
    model_config = ForecastModel.objects.filter(is_active=True).first()
    result = generate_forecast(meal_service_id, dining_hall_id, target_date, model_config)
    
    if not result:
        return None
    
    # Supersede existing active forecast
    Forecast.objects.filter(
        meal_service_id=meal_service_id,
        dining_hall_id=dining_hall_id,
        date=target_date,
        status=Forecast.Status.ACTIVE,
    ).update(status=Forecast.Status.SUPERSEDED)
    
    forecast = Forecast.objects.create(
        meal_service_id=meal_service_id,
        dining_hall_id=dining_hall_id,
        date=target_date,
        forecast_model=model_config,
        predicted_attendance=result['predicted_attendance'],
        lower_bound=result['lower_bound'],
        upper_bound=result['upper_bound'],
        weekday=result['weekday'],
        is_holiday=result['is_holiday'],
        is_exam_period=result['is_exam_period'],
        event_multiplier=result['event_multiplier'],
        historical_avg=result['historical_avg'],
        same_weekday_avg=result['same_weekday_avg'],
        data_points_used=result['data_points_used'],
        generated_by=generated_by,
    )
    return forecast


def compute_mape_for_period(meal_service_id: int, dining_hall_id: int,
                              start_date: date, end_date: date) -> Optional[float]:
    """Compute MAPE for a date range where actuals exist."""
    from forecasting.models import Forecast
    
    forecasts = Forecast.objects.filter(
        meal_service_id=meal_service_id,
        dining_hall_id=dining_hall_id,
        date__range=[start_date, end_date],
        actual_attendance__isnull=False,
        actual_attendance__gt=0,
        status=Forecast.Status.ACTIVE,
    )
    
    if not forecasts.exists():
        return None
    
    mapes = []
    for f in forecasts:
        ape = abs(f.predicted_attendance - f.actual_attendance) / f.actual_attendance * 100
        mapes.append(ape)
    
    return round(np.mean(mapes), 2) if mapes else None
