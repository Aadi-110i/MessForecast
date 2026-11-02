"""Preparation plan views and URLs with ingredient indent export"""
import csv
import json
from datetime import date
from io import StringIO
from django.urls import path
from django.http import HttpResponse
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from preparation.models import PreparationPlan, IngredientIndent, IndentItem
from analytics.serializers import PreparationPlanSerializer, IngredientIndentSerializer


class PreparationPlanListView(generics.ListAPIView):
    queryset = PreparationPlan.objects.select_related(
        'forecast__meal_service', 'forecast__dining_hall'
    ).prefetch_related('dish_items__dish')
    serializer_class = PreparationPlanSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'forecast__date', 'forecast__dining_hall']


class PreparationPlanDetailView(generics.RetrieveUpdateAPIView):
    queryset = PreparationPlan.objects.all()
    serializer_class = PreparationPlanSerializer


class IngredientIndentListView(generics.ListAPIView):
    queryset = IngredientIndent.objects.select_related('preparation_plan').prefetch_related('items__ingredient')
    serializer_class = IngredientIndentSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'date_required']


class IngredientIndentDetailView(generics.RetrieveUpdateAPIView):
    queryset = IngredientIndent.objects.all()
    serializer_class = IngredientIndentSerializer


@api_view(['POST'])
def generate_preparation_plan(request):
    """
    Generate a preparation plan from a forecast.
    POST with forecast_id and optional menu_schedule_id.
    """
    from forecasting.models import Forecast
    from preparation.models import PreparationPlan, PreparationDish
    from menu.models import MenuSchedule, MenuDish, Recipe
    
    forecast_id = request.data.get('forecast_id')
    menu_schedule_id = request.data.get('menu_schedule_id')
    
    if not forecast_id:
        return Response({'error': 'forecast_id required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        forecast = Forecast.objects.select_related('meal_service').get(pk=forecast_id)
    except Forecast.DoesNotExist:
        return Response({'error': 'Forecast not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Get or create plan
    plan, created = PreparationPlan.objects.get_or_create(
        forecast=forecast,
        defaults={
            'menu_schedule_id': menu_schedule_id,
            'planned_portions': int(
                forecast.predicted_attendance * float(forecast.meal_service.safety_margin)
            ),
            'safety_margin_used': forecast.meal_service.safety_margin,
        }
    )
    
    if created and menu_schedule_id:
        # Generate per-dish plan from menu
        try:
            schedule = MenuSchedule.objects.get(pk=menu_schedule_id)
            menu_dishes = MenuDish.objects.filter(menu=schedule.menu).select_related('dish', 'recipe')
            
            for md in menu_dishes:
                recipe = md.recipe or md.dish.recipes.filter(is_default=True).first()
                cost = 0
                if recipe:
                    cost = float(recipe.cost_per_portion) * plan.planned_portions
                
                PreparationDish.objects.create(
                    plan=plan,
                    dish=md.dish,
                    recipe=recipe,
                    portions_to_prepare=plan.planned_portions,
                    estimated_cost=cost,
                )
        except MenuSchedule.DoesNotExist:
            pass
    
    return Response(PreparationPlanSerializer(plan).data, 
                    status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(['POST'])
def generate_indent(request, plan_id):
    """Generate ingredient indent from a preparation plan."""
    from preparation.models import PreparationPlan, IngredientIndent, IndentItem
    from menu.models import RecipeItem
    from django.utils import timezone
    from decimal import Decimal
    import random, string
    
    try:
        plan = PreparationPlan.objects.prefetch_related(
            'dish_items__recipe__items__ingredient'
        ).get(pk=plan_id)
    except PreparationPlan.DoesNotExist:
        return Response({'error': 'Plan not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if hasattr(plan, 'ingredient_indent'):
        return Response(IngredientIndentSerializer(plan.ingredient_indent).data)
    
    ref = f"IND-{timezone.now():%Y%m%d}-{plan_id:04d}"
    indent = IngredientIndent.objects.create(
        preparation_plan=plan,
        reference_number=ref,
        date_required=plan.forecast.date,
        created_by=request.user,
    )
    
    # Aggregate ingredients
    ingredient_map = {}  # ingredient_id -> {'qty': X, 'unit': Y, 'cost': Z}
    
    for dish_item in plan.dish_items.all():
        if not dish_item.recipe:
            continue
        scale = Decimal(str(dish_item.portions_to_prepare)) / dish_item.recipe.portions
        
        for ri in dish_item.recipe.items.select_related('ingredient').all():
            ing_id = ri.ingredient_id
            qty = ri.quantity_per_batch * scale
            cost = qty * ri.ingredient.cost_per_unit
            
            if ing_id not in ingredient_map:
                ingredient_map[ing_id] = {
                    'ingredient': ri.ingredient,
                    'qty': Decimal('0'),
                    'unit': ri.ingredient.unit,
                    'cost': Decimal('0'),
                }
            ingredient_map[ing_id]['qty'] += qty
            ingredient_map[ing_id]['cost'] += cost
    
    total_cost = Decimal('0')
    for ing_id, data in ingredient_map.items():
        IndentItem.objects.create(
            indent=indent,
            ingredient=data['ingredient'],
            quantity_required=data['qty'].quantize(Decimal('0.001')),
            unit=data['unit'],
            estimated_cost=data['cost'].quantize(Decimal('0.01')),
        )
        total_cost += data['cost']
    
    indent.total_estimated_cost = total_cost
    indent.save(update_fields=['total_estimated_cost'])
    
    return Response(IngredientIndentSerializer(indent).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
def export_indent_csv(request, indent_id):
    """Export ingredient indent as CSV for procurement system."""
    from preparation.models import IngredientIndent
    from django.utils import timezone
    
    try:
        indent = IngredientIndent.objects.prefetch_related(
            'items__ingredient'
        ).get(pk=indent_id)
    except IngredientIndent.DoesNotExist:
        return Response({'error': 'Indent not found'}, status=status.HTTP_404_NOT_FOUND)
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="indent_{indent.reference_number}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Reference', 'Date Required', 'Ingredient Code', 'Ingredient Name',
        'Quantity', 'Unit', 'Estimated Cost (INR)', 'Procurement Code'
    ])
    
    for item in indent.items.all():
        writer.writerow([
            indent.reference_number,
            indent.date_required,
            item.ingredient.code,
            item.ingredient.name,
            float(item.quantity_required),
            item.unit,
            float(item.estimated_cost),
            item.ingredient.procurement_code,
        ])
    
    indent.exported_at = timezone.now()
    indent.export_format = 'csv'
    indent.save(update_fields=['exported_at', 'export_format'])
    
    return response


@api_view(['POST'])
def approve_plan(request, pk):
    """Approve a preparation plan."""
    from preparation.models import PreparationPlan
    from django.utils import timezone
    
    try:
        plan = PreparationPlan.objects.get(pk=pk)
    except PreparationPlan.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    
    plan.status = PreparationPlan.Status.APPROVED
    plan.approved_by = request.user
    plan.approved_at = timezone.now()
    plan.save(update_fields=['status', 'approved_by', 'approved_at'])
    
    return Response(PreparationPlanSerializer(plan).data)


urlpatterns = [
    path('', PreparationPlanListView.as_view(), name='prep-plan-list'),
    path('<int:pk>/', PreparationPlanDetailView.as_view(), name='prep-plan-detail'),
    path('<int:pk>/approve/', approve_plan, name='approve-plan'),
    path('<int:plan_id>/generate-indent/', generate_indent, name='generate-indent'),
    path('generate/', generate_preparation_plan, name='generate-plan'),
    path('indents/', IngredientIndentListView.as_view(), name='indent-list'),
    path('indents/<int:pk>/', IngredientIndentDetailView.as_view(), name='indent-detail'),
    path('indents/<int:indent_id>/export-csv/', export_indent_csv, name='export-indent-csv'),
]
