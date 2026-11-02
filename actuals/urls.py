"""Actuals views and URLs - kitchen tablet-friendly entry"""
from django.urls import path
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend

from actuals.models import ServiceActual, DishActual, WasteRecord
from analytics.serializers import ServiceActualSerializer, WasteRecordSerializer


class ServiceActualListCreateView(generics.ListCreateAPIView):
    queryset = ServiceActual.objects.select_related(
        'meal_service', 'dining_hall', 'recorded_by'
    ).prefetch_related('dish_actuals__dish')
    serializer_class = ServiceActualSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['date', 'meal_service', 'dining_hall', 'is_finalized']


class ServiceActualDetailView(generics.RetrieveUpdateAPIView):
    queryset = ServiceActual.objects.all()
    serializer_class = ServiceActualSerializer


class WasteRecordListView(generics.ListAPIView):
    queryset = WasteRecord.objects.select_related(
        'dish', 'dining_hall', 'meal_service'
    ).order_by('-date', '-total_waste_cost')
    serializer_class = WasteRecordSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['date', 'dish', 'dining_hall', 'meal_service']


@api_view(['POST'])
def finalize_actual(request, pk):
    """Finalize a service actual and trigger waste cost computation."""
    try:
        actual = ServiceActual.objects.get(pk=pk)
    except ServiceActual.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if actual.is_finalized:
        return Response({'error': 'Already finalized'}, status=status.HTTP_400_BAD_REQUEST)
    
    actual.is_finalized = True
    actual.finalized_at = timezone.now()
    actual.save(update_fields=['is_finalized', 'finalized_at'])
    
    # Trigger waste cost computation asynchronously
    try:
        from forecasting.tasks import compute_waste_costs
        compute_waste_costs.delay(actual.id)
    except Exception:
        # If Celery not available, compute synchronously
        from actuals.models import WasteRecord as WR
        for dish_actual in actual.dish_actuals.all():
            WR.compute_from_dish_actual(dish_actual)
    
    return Response(ServiceActualSerializer(actual).data)


@api_view(['GET'])
def missing_actuals(request):
    """Get list of services with missing actuals for a date."""
    from datetime import date, timedelta
    from core.models import MealService
    
    target_date = request.query_params.get('date', str(date.today() - timedelta(days=1)))
    
    services = MealService.objects.filter(is_active=True).select_related('dining_hall')
    missing = []
    
    for service in services:
        if not ServiceActual.objects.filter(meal_service=service, date=target_date).exists():
            missing.append({
                'meal_service_id': service.id,
                'meal_service_name': service.name,
                'dining_hall_id': service.dining_hall_id,
                'dining_hall_name': service.dining_hall.name,
                'date': target_date,
            })
    
    return Response({'missing': missing, 'count': len(missing)})


urlpatterns = [
    path('', ServiceActualListCreateView.as_view(), name='actual-list'),
    path('<int:pk>/', ServiceActualDetailView.as_view(), name='actual-detail'),
    path('<int:pk>/finalize/', finalize_actual, name='finalize-actual'),
    path('waste/', WasteRecordListView.as_view(), name='waste-list'),
    path('missing/', missing_actuals, name='missing-actuals'),
]
