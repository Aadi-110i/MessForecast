"""
Forecasting, Preparation, Actuals and Analytics serializers
"""
from rest_framework import serializers
from forecasting.models import Forecast, ForecastModel, ForecastAccuracyReport
from preparation.models import PreparationPlan, PreparationDish, IngredientIndent, IndentItem
from actuals.models import ServiceActual, DishActual, WasteRecord


class ForecastModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = ForecastModel
        fields = '__all__'


class ForecastSerializer(serializers.ModelSerializer):
    dining_hall_name = serializers.SerializerMethodField()
    meal_service_name = serializers.SerializerMethodField()
    confidence_range = serializers.SerializerMethodField()
    
    class Meta:
        model = Forecast
        fields = [
            'id', 'meal_service', 'meal_service_name',
            'dining_hall', 'dining_hall_name', 'date',
            'forecast_model', 'predicted_attendance',
            'lower_bound', 'upper_bound', 'confidence_range',
            'weekday', 'is_holiday', 'is_exam_period', 'event_multiplier',
            'historical_avg', 'same_weekday_avg', 'data_points_used',
            'status', 'actual_attendance', 'forecast_error', 'mape',
            'generated_at', 'generated_by'
        ]
        read_only_fields = ['id', 'generated_at']
    
    def get_dining_hall_name(self, obj):
        return obj.dining_hall.name
    
    def get_meal_service_name(self, obj):
        return obj.meal_service.name
    
    def get_confidence_range(self, obj):
        return obj.confidence_range


class ForecastAccuracySerializer(serializers.ModelSerializer):
    class Meta:
        model = ForecastAccuracyReport
        fields = '__all__'


class PreparationDishSerializer(serializers.ModelSerializer):
    dish_name = serializers.SerializerMethodField()
    
    class Meta:
        model = PreparationDish
        fields = ['id', 'dish', 'dish_name', 'recipe', 'portions_to_prepare', 'estimated_cost']
    
    def get_dish_name(self, obj):
        return obj.dish.name


class PreparationPlanSerializer(serializers.ModelSerializer):
    dish_items = PreparationDishSerializer(many=True, read_only=True)
    dining_hall_name = serializers.SerializerMethodField()
    meal_service_name = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()
    predicted_attendance = serializers.SerializerMethodField()
    
    class Meta:
        model = PreparationPlan
        fields = [
            'id', 'forecast', 'menu_schedule', 'planned_portions',
            'safety_margin_used', 'status', 'date',
            'predicted_attendance', 'dining_hall_name', 'meal_service_name',
            'dish_items', 'notes', 'approved_by', 'approved_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_dining_hall_name(self, obj):
        return obj.forecast.dining_hall.name
    
    def get_meal_service_name(self, obj):
        return obj.forecast.meal_service.name
    
    def get_date(self, obj):
        return obj.forecast.date
    
    def get_predicted_attendance(self, obj):
        return obj.forecast.predicted_attendance


class IndentItemSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.SerializerMethodField()
    
    class Meta:
        model = IndentItem
        fields = [
            'id', 'ingredient', 'ingredient_name', 'quantity_required',
            'unit', 'estimated_cost', 'quantity_fulfilled', 'is_fulfilled'
        ]
    
    def get_ingredient_name(self, obj):
        return obj.ingredient.name


class IngredientIndentSerializer(serializers.ModelSerializer):
    items = IndentItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = IngredientIndent
        fields = [
            'id', 'preparation_plan', 'reference_number',
            'date_required', 'status', 'total_estimated_cost',
            'exported_at', 'export_format', 'created_by',
            'items', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'reference_number', 'created_by', 'created_at', 'updated_at']


class DishActualSerializer(serializers.ModelSerializer):
    dish_name = serializers.SerializerMethodField()
    portions_leftover = serializers.SerializerMethodField()
    waste_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = DishActual
        fields = [
            'id', 'dish', 'dish_name', 'recipe',
            'portions_prepared', 'portions_served',
            'portions_leftover', 'waste_percentage', 'waste_weight_kg'
        ]
    
    def get_dish_name(self, obj):
        return obj.dish.name
    
    def get_portions_leftover(self, obj):
        return obj.portions_leftover
    
    def get_waste_percentage(self, obj):
        return round(obj.waste_percentage, 1)


class ServiceActualSerializer(serializers.ModelSerializer):
    dish_actuals = DishActualSerializer(many=True, required=False)
    dining_hall_name = serializers.SerializerMethodField()
    meal_service_name = serializers.SerializerMethodField()
    total_prepared_portions = serializers.SerializerMethodField()
    total_served_portions = serializers.SerializerMethodField()
    total_waste_portions = serializers.SerializerMethodField()
    
    class Meta:
        model = ServiceActual
        fields = [
            'id', 'meal_service', 'meal_service_name',
            'dining_hall', 'dining_hall_name', 'date',
            'preparation_plan', 'actual_attendance',
            'dish_actuals', 'total_prepared_portions',
            'total_served_portions', 'total_waste_portions',
            'is_finalized', 'finalized_at', 'notes',
            'recorded_by', 'recorded_at'
        ]
        read_only_fields = ['id', 'recorded_by', 'recorded_at']
    
    def get_dining_hall_name(self, obj):
        return obj.dining_hall.name
    
    def get_meal_service_name(self, obj):
        return obj.meal_service.name
    
    def get_total_prepared_portions(self, obj):
        return obj.total_prepared_portions
    
    def get_total_served_portions(self, obj):
        return obj.total_served_portions
    
    def get_total_waste_portions(self, obj):
        return obj.total_waste_portions
    
    def create(self, validated_data):
        dish_actuals_data = validated_data.pop('dish_actuals', [])
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['recorded_by'] = request.user
        
        actual = ServiceActual.objects.create(**validated_data)
        for da_data in dish_actuals_data:
            DishActual.objects.create(service_actual=actual, **da_data)
        return actual
    
    def update(self, instance, validated_data):
        dish_actuals_data = validated_data.pop('dish_actuals', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if dish_actuals_data is not None:
            instance.dish_actuals.all().delete()
            for da_data in dish_actuals_data:
                DishActual.objects.create(service_actual=instance, **da_data)
        
        return instance


class WasteRecordSerializer(serializers.ModelSerializer):
    dish_name = serializers.SerializerMethodField()
    dining_hall_name = serializers.SerializerMethodField()
    meal_service_name = serializers.SerializerMethodField()
    
    class Meta:
        model = WasteRecord
        fields = [
            'id', 'dish', 'dish_name', 'dining_hall', 'dining_hall_name',
            'meal_service', 'meal_service_name', 'date',
            'portions_wasted', 'weight_wasted_kg',
            'ingredient_cost_per_portion', 'total_waste_cost',
            'over_preparation_cost', 'computed_at'
        ]
    
    def get_dish_name(self, obj):
        return obj.dish.name
    
    def get_dining_hall_name(self, obj):
        return obj.dining_hall.name
    
    def get_meal_service_name(self, obj):
        return obj.meal_service.name
