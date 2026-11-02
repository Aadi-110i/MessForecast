"""Forecasting views and URLs"""
from datetime import date, timedelta
from django.urls import path
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from forecasting.models import Forecast, ForecastModel, ForecastAccuracyReport
from analytics.serializers import ForecastSerializer, ForecastModelSerializer, ForecastAccuracySerializer


class ForecastListView(generics.ListAPIView):
    queryset = Forecast.objects.select_related('meal_service', 'dining_hall').filter(
        status=Forecast.Status.ACTIVE
    )
    serializer_class = ForecastSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['date', 'meal_service', 'dining_hall', 'status']


class ForecastDetailView(generics.RetrieveAPIView):
    queryset = Forecast.objects.all()
    serializer_class = ForecastSerializer


class ForecastModelListView(generics.ListCreateAPIView):
    queryset = ForecastModel.objects.all()
    serializer_class = ForecastModelSerializer


class ForecastAccuracyListView(generics.ListAPIView):
    queryset = ForecastAccuracyReport.objects.select_related('meal_service', 'dining_hall')
    serializer_class = ForecastAccuracySerializer
    filterset_fields = ['period_type', 'meal_service', 'dining_hall']


@api_view(['POST'])
def generate_forecast_view(request):
    """Manually trigger forecast generation."""
    meal_service_id = request.data.get('meal_service_id')
    dining_hall_id = request.data.get('dining_hall_id')
    target_date_str = request.data.get('date')
    
    if not all([meal_service_id, dining_hall_id, target_date_str]):
        return Response(
            {'error': 'meal_service_id, dining_hall_id, and date required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        target_date = date.fromisoformat(target_date_str)
    except ValueError:
        return Response({'error': 'Invalid date format'}, status=status.HTTP_400_BAD_REQUEST)
    
    from forecasting.engine import save_forecast
    forecast = save_forecast(meal_service_id, dining_hall_id, target_date, 
                              request.user.username)
    
    if not forecast:
        return Response({'error': 'Forecast generation failed'}, 
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response(ForecastSerializer(forecast).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def generate_7day_view(request):
    """Generate 7-day forecasts for a meal service."""
    meal_service_id = request.data.get('meal_service_id')
    dining_hall_id = request.data.get('dining_hall_id')
    
    if not all([meal_service_id, dining_hall_id]):
        return Response(
            {'error': 'meal_service_id and dining_hall_id required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    from forecasting.tasks import generate_daily_forecasts
    # Generate synchronously for now (use task in production)
    from forecasting.engine import save_forecast
    from core.models import MealService
    
    tomorrow = date.today() + timedelta(days=1)
    generated = []
    
    for i in range(7):
        target = tomorrow + timedelta(days=i)
        forecast = save_forecast(meal_service_id, dining_hall_id, target, request.user.username)
        if forecast:
            generated.append(ForecastSerializer(forecast).data)
    
    return Response({'generated': len(generated), 'forecasts': generated})


@api_view(['GET'])
def forecast_explanation(request, pk):
    """Get plain-language explanation of a forecast for mess managers."""
    try:
        forecast = Forecast.objects.select_related('forecast_model').get(pk=pk)
    except Forecast.DoesNotExist:
        return Response({'error': 'Forecast not found'}, status=status.HTTP_404_NOT_FOUND)
    
    model = forecast.forecast_model
    method_desc = "Weighted Moving Average" if model else "Weighted Moving Average"
    
    explanation = {
        'forecast_id': forecast.id,
        'predicted_attendance': forecast.predicted_attendance,
        'confidence_range': f"{forecast.lower_bound} – {forecast.upper_bound}",
        'method': method_desc,
        'plain_language': (
            f"We looked at the last {getattr(model, 'lookback_days', 28)} days of attendance "
            f"for this meal service. "
            f"We used {forecast.data_points_used} meal records. "
            f"The typical attendance on {['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][forecast.weekday]}s "
            f"is {forecast.same_weekday_avg or 'unknown'} students. "
            f"Recent trend shows {forecast.historical_avg or 'no data yet'} on average. "
            + (f"A calendar event adjusts this by {float(forecast.event_multiplier):.0%}. " 
               if forecast.event_multiplier != 1 else "")
            + f"The forecast is {forecast.predicted_attendance} students, "
            f"with a range of {forecast.lower_bound}–{forecast.upper_bound}."
        ),
        'factors': {
            'historical_avg': float(forecast.historical_avg) if forecast.historical_avg else None,
            'same_weekday_avg': float(forecast.same_weekday_avg) if forecast.same_weekday_avg else None,
            'event_multiplier': float(forecast.event_multiplier),
            'is_holiday': forecast.is_holiday,
            'is_exam_period': forecast.is_exam_period,
            'data_points': forecast.data_points_used,
        },
        'accuracy': {
            'actual': forecast.actual_attendance,
            'error': float(forecast.forecast_error) if forecast.forecast_error else None,
            'mape': float(forecast.mape) if forecast.mape else None,
        } if forecast.actual_attendance else None,
    }
    return Response(explanation)


urlpatterns = [
    path('', ForecastListView.as_view(), name='forecast-list'),
    path('<int:pk>/', ForecastDetailView.as_view(), name='forecast-detail'),
    path('<int:pk>/explanation/', forecast_explanation, name='forecast-explanation'),
    path('generate/', generate_forecast_view, name='generate-forecast'),
    path('generate-7day/', generate_7day_view, name='generate-7day'),
    path('models/', ForecastModelListView.as_view(), name='forecast-model-list'),
    path('accuracy/', ForecastAccuracyListView.as_view(), name='forecast-accuracy-list'),
]
