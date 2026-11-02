"""Analytics views and URLs - waste reporting, MAPE, top-10 waste dishes"""
from datetime import date, timedelta
from django.urls import path
from django.db.models import Sum, Avg, Count, F, ExpressionWrapper, DecimalField
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status


@api_view(['GET'])
def waste_summary(request):
    """
    Waste summary by dish, meal, hall and period.
    Query params: start_date, end_date, dining_hall_id, meal_service_id
    """
    from actuals.models import WasteRecord
    
    start = request.query_params.get('start_date', str(date.today() - timedelta(days=30)))
    end = request.query_params.get('end_date', str(date.today()))
    hall_id = request.query_params.get('dining_hall_id')
    service_id = request.query_params.get('meal_service_id')
    
    qs = WasteRecord.objects.filter(date__range=[start, end])
    if hall_id:
        qs = qs.filter(dining_hall_id=hall_id)
    if service_id:
        qs = qs.filter(meal_service_id=service_id)
    
    by_dish = qs.values('dish__name', 'dish_id').annotate(
        total_portions_wasted=Sum('portions_wasted'),
        total_weight_kg=Sum('weight_wasted_kg'),
        total_cost=Sum('total_waste_cost'),
        records_count=Count('id'),
    ).order_by('-total_cost')
    
    by_meal_service = qs.values('meal_service__name', 'meal_service_id').annotate(
        total_portions_wasted=Sum('portions_wasted'),
        total_cost=Sum('total_waste_cost'),
    ).order_by('-total_cost')
    
    by_hall = qs.values('dining_hall__name', 'dining_hall_id').annotate(
        total_portions_wasted=Sum('portions_wasted'),
        total_cost=Sum('total_waste_cost'),
    ).order_by('-total_cost')
    
    totals = qs.aggregate(
        total_portions=Sum('portions_wasted'),
        total_weight=Sum('weight_wasted_kg'),
        total_cost=Sum('total_waste_cost'),
    )
    
    return Response({
        'period': {'start': start, 'end': end},
        'totals': totals,
        'by_dish': list(by_dish),
        'by_meal_service': list(by_meal_service),
        'by_hall': list(by_hall),
    })


@api_view(['GET'])
def top_waste_dishes(request):
    """Top-10 waste dishes by cost."""
    from actuals.models import WasteRecord
    
    days = int(request.query_params.get('days', 30))
    start = date.today() - timedelta(days=days)
    limit = int(request.query_params.get('limit', 10))
    
    top = WasteRecord.objects.filter(date__gte=start).values(
        'dish__name', 'dish_id'
    ).annotate(
        total_cost=Sum('total_waste_cost'),
        total_portions=Sum('portions_wasted'),
        occurrences=Count('id'),
        avg_cost_per_service=Avg('total_waste_cost'),
    ).order_by('-total_cost')[:limit]
    
    return Response({'top_waste_dishes': list(top), 'period_days': days})


@api_view(['GET'])
def forecast_accuracy_summary(request):
    """MAPE summary by meal and hall."""
    from forecasting.models import Forecast
    
    start = request.query_params.get('start_date', str(date.today() - timedelta(days=56)))  # 8 weeks
    end = request.query_params.get('end_date', str(date.today()))
    
    qs = Forecast.objects.filter(
        date__range=[start, end],
        mape__isnull=False,
        status=Forecast.Status.ACTIVE,
    )
    
    by_service = qs.values('meal_service__name', 'meal_service_id').annotate(
        mean_mape=Avg('mape'),
        count=Count('id'),
    ).order_by('meal_service__name')
    
    by_hall = qs.values('dining_hall__name', 'dining_hall_id').annotate(
        mean_mape=Avg('mape'),
        count=Count('id'),
    ).order_by('dining_hall__name')
    
    overall = qs.aggregate(mean_mape=Avg('mape'), count=Count('id'))
    
    # Weekly trend
    weekly = qs.annotate(week=TruncWeek('date')).values('week').annotate(
        mean_mape=Avg('mape'),
        count=Count('id'),
    ).order_by('week')
    
    return Response({
        'period': {'start': start, 'end': end},
        'overall': overall,
        'by_meal_service': list(by_service),
        'by_hall': list(by_hall),
        'weekly_trend': list(weekly),
    })


@api_view(['GET'])
def attendance_patterns(request):
    """Attendance patterns by weekday, event, and exam period."""
    from attendance.models import AttendanceSummary
    
    days = int(request.query_params.get('days', 90))
    start = date.today() - timedelta(days=days)
    meal_service_id = request.query_params.get('meal_service_id')
    hall_id = request.query_params.get('dining_hall_id')
    
    qs = AttendanceSummary.objects.filter(date__gte=start, finalized=True)
    if meal_service_id:
        qs = qs.filter(meal_service_id=meal_service_id)
    if hall_id:
        qs = qs.filter(dining_hall_id=hall_id)
    
    by_weekday = qs.values('day_of_week').annotate(
        avg_count=Avg('valid_count'),
        count=Count('id'),
    ).order_by('day_of_week')
    
    holiday_vs_normal = qs.values('is_holiday').annotate(
        avg_count=Avg('valid_count'),
        count=Count('id'),
    )
    
    exam_vs_normal = qs.values('is_exam_period').annotate(
        avg_count=Avg('valid_count'),
        count=Count('id'),
    )
    
    event_vs_normal = qs.values('is_event_day').annotate(
        avg_count=Avg('valid_count'),
        count=Count('id'),
    )
    
    return Response({
        'by_weekday': list(by_weekday),
        'holiday_comparison': list(holiday_vs_normal),
        'exam_period_comparison': list(exam_vs_normal),
        'event_day_comparison': list(event_vs_normal),
    })


@api_view(['GET'])
def cost_saving_trend(request):
    """Cost savings trend: comparing current waste to baseline."""
    from actuals.models import WasteRecord
    
    # Monthly aggregation
    months = int(request.query_params.get('months', 6))
    start = date.today() - timedelta(days=30 * months)
    
    monthly = WasteRecord.objects.filter(date__gte=start).annotate(
        month=TruncMonth('date')
    ).values('month').annotate(
        total_waste_cost=Sum('total_waste_cost'),
        total_portions=Sum('portions_wasted'),
        count=Count('id'),
    ).order_by('month')
    
    return Response({'monthly_waste': list(monthly), 'months': months})


@api_view(['GET'])
def ingredient_consumption_vs_indent(request):
    """Compare actual ingredient usage against planned indent."""
    from preparation.models import IngredientIndent, IndentItem
    
    start = request.query_params.get('start_date', str(date.today() - timedelta(days=30)))
    end = request.query_params.get('end_date', str(date.today()))
    
    indents = IngredientIndent.objects.filter(
        date_required__range=[start, end],
        status__in=['fulfilled', 'partial']
    ).prefetch_related('items__ingredient')
    
    results = []
    for indent in indents:
        for item in indent.items.all():
            results.append({
                'reference': indent.reference_number,
                'date': indent.date_required,
                'ingredient': item.ingredient.name,
                'planned_qty': float(item.quantity_required),
                'fulfilled_qty': float(item.quantity_fulfilled),
                'unit': item.unit,
                'fulfillment_pct': round(
                    float(item.quantity_fulfilled) / float(item.quantity_required) * 100, 1
                ) if item.quantity_required > 0 else 0,
            })
    
    return Response({'results': results, 'period': {'start': start, 'end': end}})


@api_view(['GET'])
def dashboard_summary(request):
    """Combined dashboard summary for mess manager home screen."""
    from actuals.models import WasteRecord
    from forecasting.models import Forecast
    from attendance.models import AttendanceSummary
    
    today = date.today()
    yesterday = today - timedelta(days=1)
    this_month_start = today.replace(day=1)
    
    # Today's forecasts
    todays_forecasts = Forecast.objects.filter(
        date=today, status=Forecast.Status.ACTIVE
    ).select_related('meal_service', 'dining_hall')
    
    # Yesterday's waste
    yesterdays_waste = WasteRecord.objects.filter(date=yesterday).aggregate(
        total_cost=Sum('total_waste_cost'),
        total_portions=Sum('portions_wasted'),
    )
    
    # This month's waste
    monthly_waste = WasteRecord.objects.filter(date__gte=this_month_start).aggregate(
        total_cost=Sum('total_waste_cost'),
        total_portions=Sum('portions_wasted'),
    )
    
    # Forecast accuracy (last 7 days)
    recent_mape = Forecast.objects.filter(
        date__gte=today - timedelta(days=7),
        mape__isnull=False,
    ).aggregate(mean_mape=Avg('mape'))
    
    from forecasting.serializers_light import ForecastLightSerializer
    
    return Response({
        'todays_forecasts': [
            {
                'meal_service': f.meal_service.name,
                'dining_hall': f.dining_hall.name,
                'predicted': f.predicted_attendance,
                'range': f"{f.lower_bound}–{f.upper_bound}",
            } for f in todays_forecasts
        ],
        'yesterdays_waste': yesterdays_waste,
        'monthly_waste': monthly_waste,
        'forecast_accuracy_7d': recent_mape,
        'date': str(today),
    })


urlpatterns = [
    path('waste/', waste_summary, name='waste-summary'),
    path('waste/top-dishes/', top_waste_dishes, name='top-waste-dishes'),
    path('forecast-accuracy/', forecast_accuracy_summary, name='forecast-accuracy-summary'),
    path('attendance-patterns/', attendance_patterns, name='attendance-patterns'),
    path('cost-savings/', cost_saving_trend, name='cost-saving-trend'),
    path('ingredient-consumption/', ingredient_consumption_vs_indent, name='ingredient-consumption'),
    path('dashboard/', dashboard_summary, name='dashboard-summary'),
]
