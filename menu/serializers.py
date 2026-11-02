"""
Menu serializers
"""
from rest_framework import serializers
from menu.models import Ingredient, Dish, Recipe, RecipeItem, Menu, MenuDish, MenuSchedule


class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = '__all__'


class RecipeItemSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.SerializerMethodField()
    ingredient_unit = serializers.SerializerMethodField()
    cost_per_batch = serializers.SerializerMethodField()
    
    class Meta:
        model = RecipeItem
        fields = [
            'id', 'ingredient', 'ingredient_name', 'ingredient_unit',
            'quantity_per_batch', 'is_optional', 'notes',
            'cost_per_batch'
        ]
    
    def get_ingredient_name(self, obj):
        return obj.ingredient.name
    
    def get_ingredient_unit(self, obj):
        return obj.ingredient.unit
    
    def get_cost_per_batch(self, obj):
        return float(obj.cost_per_batch)


class RecipeSerializer(serializers.ModelSerializer):
    items = RecipeItemSerializer(many=True, read_only=True)
    cost_per_portion = serializers.SerializerMethodField()
    
    class Meta:
        model = Recipe
        fields = [
            'id', 'dish', 'name', 'portions', 'portion_size_grams',
            'preparation_time_minutes', 'is_default', 'notes',
            'cost_per_portion', 'items', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_cost_per_portion(self, obj):
        return float(obj.cost_per_portion)


class DishSerializer(serializers.ModelSerializer):
    recipes = RecipeSerializer(many=True, read_only=True)
    category_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Dish
        fields = [
            'id', 'name', 'code', 'category', 'category_display',
            'description', 'is_vegetarian', 'is_vegan',
            'allergens', 'is_active', 'image', 'recipes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_category_display(self, obj):
        return obj.get_category_display()


class DishListSerializer(serializers.ModelSerializer):
    """Lightweight dish serializer for list views."""
    class Meta:
        model = Dish
        fields = ['id', 'name', 'code', 'category', 'is_vegetarian', 'is_vegan', 'is_active']


class MenuDishSerializer(serializers.ModelSerializer):
    dish_name = serializers.SerializerMethodField()
    
    class Meta:
        model = MenuDish
        fields = [
            'id', 'dish', 'dish_name', 'recipe', 'is_main', 'serving_order'
        ]
    
    def get_dish_name(self, obj):
        return obj.dish.name


class MenuSerializer(serializers.ModelSerializer):
    dishes_detail = MenuDishSerializer(source='menudish_set', many=True, read_only=True)
    dining_hall_name = serializers.SerializerMethodField()
    meal_service_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Menu
        fields = [
            'id', 'name', 'dining_hall', 'dining_hall_name',
            'meal_service', 'meal_service_name', 'dishes', 'dishes_detail',
            'is_published', 'notes', 'created_by',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']
    
    def get_dining_hall_name(self, obj):
        return obj.dining_hall.name
    
    def get_meal_service_name(self, obj):
        return obj.meal_service.name
    
    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class MenuScheduleSerializer(serializers.ModelSerializer):
    menu_name = serializers.SerializerMethodField()
    
    class Meta:
        model = MenuSchedule
        fields = [
            'id', 'menu', 'menu_name', 'date', 'is_active',
            'expected_attendance', 'created_by', 'created_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at']
    
    def get_menu_name(self, obj):
        return obj.menu.name
    
    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)
