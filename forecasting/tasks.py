"""
Celery tasks for scheduled forecasting and reporting.
"""
import logging
from datetime import date, timedelta
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='forecasting.generate_daily_forecasts')
def generate_daily_forecasts(self):
    """
    Daily task: generate 7-day forecasts for all active meal services.
    Runs at 23:00 each day via Celery Beat.
    """
    from core.models import MealService, DiningHall
    from forecasting.engine import save_forecast
    
    services = MealService.objects.filter(is_active=True).select_related('dining_hall')
    count = 0
    errors = 0
    
    tomorrow = date.today() + timedelta(days=1)
    
    for service in services:
        for day_offset in range(7):
            target = tomorrow + timedelta(days=day_offset)
            try:
                forecast = save_forecast(
                    service.id, service.dining_hall_id, target, 'celery_daily'
                )
                if forecast:
                    count += 1
            except Exception as e:
                logger.error(f"Forecast failed for service={service.id} date={target}: {e}")
                errors += 1
    
    logger.info(f"Daily forecasts generated: {count} ok, {errors} errors")
    return {'generated': count, 'errors': errors}


@shared_task(bind=True, name='forecasting.compute_forecast_accuracy')
def compute_forecast_accuracy(self):
    """
    After each service window, update forecast accuracy with actuals.
    """
    from forecasting.models import Forecast
    from actuals.models import ServiceActual
    
    # Find forecasts for yesterday that don't have accuracy computed yet
    yesterday = date.today() - timedelta(days=1)
    
    forecasts_needing_accuracy = Forecast.objects.filter(
        date=yesterday,
        actual_attendance__isnull=True,
        status=Forecast.Status.ACTIVE,
    )
    
    updated = 0
    for forecast in forecasts_needing_accuracy:
        try:
            actual = ServiceActual.objects.get(
                meal_service=forecast.meal_service,
                dining_hall=forecast.dining_hall,
                date=forecast.date,
                is_finalized=True,
            )
            forecast.actual_attendance = actual.actual_attendance
            forecast.save(update_fields=['actual_attendance'])
            forecast.compute_accuracy()
            updated += 1
        except ServiceActual.DoesNotExist:
            pass
        except Exception as e:
            logger.error(f"Accuracy compute error for forecast {forecast.id}: {e}")
    
    logger.info(f"Accuracy computed for {updated} forecasts")
    return {'updated': updated}


@shared_task(bind=True, name='forecasting.generate_accuracy_report')
def generate_accuracy_report(self, period_type='weekly'):
    """
    Generate MAPE accuracy report for a period.
    """
    from core.models import MealService
    from forecasting.engine import compute_mape_for_period
    from forecasting.models import ForecastAccuracyReport, Forecast
    import numpy as np
    
    if period_type == 'weekly':
        today = date.today()
        period_end = today - timedelta(days=today.weekday() + 1)
        period_start = period_end - timedelta(days=6)
    else:
        period_end = date.today().replace(day=1) - timedelta(days=1)
        period_start = period_end.replace(day=1)
    
    services = MealService.objects.filter(is_active=True).select_related('dining_hall')
    created = 0
    
    for service in services:
        forecasts = Forecast.objects.filter(
            meal_service=service,
            dining_hall=service.dining_hall,
            date__range=[period_start, period_end],
            actual_attendance__isnull=False,
            actual_attendance__gt=0,
        )
        
        if not forecasts.exists():
            continue
        
        mapes = []
        for f in forecasts:
            if f.mape is not None:
                mapes.append(float(f.mape))
        
        if not mapes:
            continue
        
        report, _ = ForecastAccuracyReport.objects.update_or_create(
            meal_service=service,
            dining_hall=service.dining_hall,
            period_type=period_type,
            period_start=period_start,
            defaults={
                'period_end': period_end,
                'forecasts_count': len(mapes),
                'mean_mape': round(np.mean(mapes), 2),
                'median_mape': round(np.median(mapes), 2),
                'max_mape': round(np.max(mapes), 2),
                'min_mape': round(np.min(mapes), 2),
            }
        )
        created += 1
    
    return {'reports_created': created}


@shared_task(bind=True, name='actuals.compute_waste_costs')
def compute_waste_costs(self, service_actual_id: int):
    """Compute waste costs for a finalized service actual."""
    from actuals.models import ServiceActual, WasteRecord
    
    try:
        actual = ServiceActual.objects.get(pk=service_actual_id, is_finalized=True)
    except ServiceActual.DoesNotExist:
        logger.error(f"ServiceActual {service_actual_id} not found or not finalized")
        return
    
    computed = 0
    for dish_actual in actual.dish_actuals.select_related('dish', 'recipe'):
        WasteRecord.compute_from_dish_actual(dish_actual)
        computed += 1
    
    # Update forecast actuals
    from forecasting.models import Forecast
    try:
        forecast = Forecast.objects.get(
            meal_service=actual.meal_service,
            dining_hall=actual.dining_hall,
            date=actual.date,
            status=Forecast.Status.ACTIVE,
        )
        forecast.actual_attendance = actual.actual_attendance
        forecast.save(update_fields=['actual_attendance'])
        forecast.compute_accuracy()
    except Forecast.DoesNotExist:
        pass
    
    # Finalize attendance summary
    from attendance.models import AttendanceSummary
    try:
        summary = AttendanceSummary.objects.get(
            meal_service=actual.meal_service,
            dining_hall=actual.dining_hall,
            date=actual.date,
        )
        summary.finalized = True
        summary.finalized_at = timezone.now()
        summary.save(update_fields=['finalized', 'finalized_at'])
    except AttendanceSummary.DoesNotExist:
        pass
    
    logger.info(f"Waste costs computed for ServiceActual {service_actual_id}: {computed} dishes")
    return {'dishes_computed': computed}


@shared_task(bind=True, name='notifications.send_daily_kitchen_guidance')
def send_daily_kitchen_guidance(self):
    """Send daily preparation guidance to kitchen staff."""
    from core.models import MealService, User
    from forecasting.models import Forecast
    from preparation.models import PreparationPlan
    
    tomorrow = date.today() + timedelta(days=1)
    
    services = MealService.objects.filter(is_active=True).select_related('dining_hall')
    sent = 0
    
    for service in services:
        try:
            forecast = Forecast.objects.get(
                meal_service=service,
                dining_hall=service.dining_hall,
                date=tomorrow,
                status=Forecast.Status.ACTIVE,
            )
            # In production: send push notification / email to kitchen staff
            logger.info(f"Kitchen guidance for {service}: {forecast.predicted_attendance} portions tomorrow")
            sent += 1
        except Forecast.DoesNotExist:
            pass
    
    return {'notifications_sent': sent}


@shared_task(bind=True, name='notifications.missing_actuals_reminder')
def missing_actuals_reminder(self):
    """Remind kitchen staff to record actuals for past services."""
    from core.models import MealService
    from actuals.models import ServiceActual
    
    # Find services from yesterday with no actuals
    yesterday = date.today() - timedelta(days=1)
    services = MealService.objects.filter(is_active=True)
    missing = []
    
    for service in services:
        if not ServiceActual.objects.filter(
            meal_service=service, date=yesterday
        ).exists():
            missing.append(str(service))
    
    if missing:
        logger.warning(f"Missing actuals for {yesterday}: {', '.join(missing)}")
    
    return {'missing_services': missing}
