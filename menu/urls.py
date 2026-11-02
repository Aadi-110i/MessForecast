"""Menu views and URLs"""
from django.urls import path
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from menu.models import Ingredient, Dish, Recipe, RecipeItem, Menu, MenuSchedule
from menu.serializers import (
    IngredientSerializer, DishSerializer, DishListSerializer,
    RecipeSerializer, MenuSerializer, MenuScheduleSerializer
)


class IngredientListCreateView(generics.ListCreateAPIView):
    queryset = Ingredient.objects.filter(is_active=True)
    serializer_class = IngredientSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'unit', 'is_active']
    search_fields = ['name', 'code', 'supplier']
    ordering_fields = ['name', 'category', 'cost_per_unit']


class IngredientDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Ingredient.objects.all()
    serializer_class = IngredientSerializer


class DishListCreateView(generics.ListCreateAPIView):
    queryset = Dish.objects.filter(is_active=True)
    serializer_class = DishListSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'is_vegetarian', 'is_vegan', 'is_active']
    search_fields = ['name', 'code', 'description']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return DishSerializer
        return DishListSerializer


class DishDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Dish.objects.all()
    serializer_class = DishSerializer


class RecipeListCreateView(generics.ListCreateAPIView):
    queryset = Recipe.objects.select_related('dish').prefetch_related('items__ingredient')
    serializer_class = RecipeSerializer
    filterset_fields = ['dish', 'is_default']


class RecipeDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Recipe.objects.all()
    serializer_class = RecipeSerializer


class MenuListCreateView(generics.ListCreateAPIView):
    queryset = Menu.objects.select_related('dining_hall', 'meal_service').prefetch_related('dishes')
    serializer_class = MenuSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['dining_hall', 'meal_service', 'is_published']
    search_fields = ['name']


class MenuDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Menu.objects.all()
    serializer_class = MenuSerializer


class MenuScheduleListCreateView(generics.ListCreateAPIView):
    queryset = MenuSchedule.objects.select_related('menu').order_by('date')
    serializer_class = MenuScheduleSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['menu', 'date', 'is_active']


class MenuScheduleDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = MenuSchedule.objects.all()
    serializer_class = MenuScheduleSerializer


@api_view(['GET'])
def menu_calendar(request):
    """Get menu schedule for a date range (for calendar view)."""
    from datetime import date, timedelta
    from menu.models import MenuSchedule
    
    start = request.query_params.get('start', str(date.today()))
    end = request.query_params.get('end', str(date.today() + timedelta(days=7)))
    hall_id = request.query_params.get('dining_hall')
    
    qs = MenuSchedule.objects.filter(
        date__range=[start, end], is_active=True
    ).select_related('menu', 'menu__dining_hall', 'menu__meal_service')
    
    if hall_id:
        qs = qs.filter(menu__dining_hall_id=hall_id)
    
    serializer = MenuScheduleSerializer(qs, many=True)
    return Response(serializer.data)


urlpatterns = [
    path('ingredients/', IngredientListCreateView.as_view(), name='ingredient-list'),
    path('ingredients/<int:pk>/', IngredientDetailView.as_view(), name='ingredient-detail'),
    path('dishes/', DishListCreateView.as_view(), name='dish-list'),
    path('dishes/<int:pk>/', DishDetailView.as_view(), name='dish-detail'),
    path('recipes/', RecipeListCreateView.as_view(), name='recipe-list'),
    path('recipes/<int:pk>/', RecipeDetailView.as_view(), name='recipe-detail'),
    path('', MenuListCreateView.as_view(), name='menu-list'),
    path('<int:pk>/', MenuDetailView.as_view(), name='menu-detail'),
    path('schedules/', MenuScheduleListCreateView.as_view(), name='menu-schedule-list'),
    path('schedules/<int:pk>/', MenuScheduleDetailView.as_view(), name='menu-schedule-detail'),
    path('calendar/', menu_calendar, name='menu-calendar'),
]
