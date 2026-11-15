"""Serializers for the REST API.

The API is the integration surface: the PWA, the RFID gateway and the
procurement export all speak to it.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.actuals.models import DishActual, ServiceActual
from apps.attendance.models import AttendanceRecord, MealService
from apps.catalog.models import CostRate, DiningHall, Dish, Ingredient, Recipe, RecipeItem
from apps.events.models import CalendarEvent, ServiceLevelConfig
from apps.forecasting.models import Forecast
from apps.menu.models import Menu, MenuItem, MenuSchedule
from apps.notifications.models import Notification
from apps.planning.models import IndentLine, IngredientIndent, PreparationLine, PreparationPlan
from apps.waste.models import WasteRecord


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

class DiningHallSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiningHall
        fields = ["id", "name", "code", "capacity", "is_active", "notes"]


class IngredientSerializer(serializers.ModelSerializer):
    current_unit_cost = serializers.SerializerMethodField()

    class Meta:
        model = Ingredient
        fields = [
            "id", "name", "code", "base_unit", "purchase_pack_size",
            "purchase_pack_unit", "category", "is_active", "current_unit_cost",
        ]

    def get_current_unit_cost(self, obj) -> str:
        return str(obj.unit_cost())


class RecipeItemSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    gross_quantity = serializers.DecimalField(max_digits=14, decimal_places=4, read_only=True)

    class Meta:
        model = RecipeItem
        fields = ["id", "ingredient", "ingredient_name", "quantity", "trim_loss_pct", "gross_quantity"]


class RecipeSerializer(serializers.ModelSerializer):
    items = RecipeItemSerializer(many=True, read_only=True)
    dish_name = serializers.CharField(source="dish.name", read_only=True)
    cost_per_portion = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = [
            "id", "dish", "dish_name", "version", "effective_from", "effective_to",
            "notes", "is_active", "items", "cost_per_portion",
        ]

    def get_cost_per_portion(self, obj) -> str:
        return str(obj.cost_per_portion())


class DishSerializer(serializers.ModelSerializer):
    cost_per_portion = serializers.SerializerMethodField()

    class Meta:
        model = Dish
        fields = [
            "id", "name", "code", "category", "serving_size_g",
            "direct_unit_cost", "is_active", "cost_per_portion",
        ]

    def get_cost_per_portion(self, obj) -> str:
        return str(obj.cost_per_portion())


class CostRateSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    hall_code = serializers.CharField(source="hall.code", read_only=True, default=None)

    class Meta:
        model = CostRate
        fields = [
            "id", "ingredient", "ingredient_name", "hall", "hall_code",
            "unit_cost", "effective_from", "effective_to", "source",
        ]


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

class MenuItemSerializer(serializers.ModelSerializer):
    dish_name = serializers.CharField(source="dish.name", read_only=True)

    class Meta:
        model = MenuItem
        fields = ["id", "menu", "meal", "dish", "dish_name", "sequence", "expected_share"]


class MenuSerializer(serializers.ModelSerializer):
    items = MenuItemSerializer(many=True, read_only=True)

    class Meta:
        model = Menu
        fields = ["id", "name", "code", "cycle_label", "description", "is_active", "items"]


class MenuScheduleSerializer(serializers.ModelSerializer):
    menu_name = serializers.CharField(source="menu.name", read_only=True)
    hall_name = serializers.CharField(source="hall.name", read_only=True)
    dishes = serializers.SerializerMethodField()

    class Meta:
        model = MenuSchedule
        fields = [
            "id", "menu", "menu_name", "hall", "hall_name", "date", "meal",
            "is_published", "published_at", "notes", "dishes",
        ]

    def get_dishes(self, obj) -> list:
        return [
            {"dish": item.dish.name, "code": item.dish.code, "meal": item.meal}
            for item in obj.menu.items_for_meal(obj.meal)
        ]


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

class MealServiceSerializer(serializers.ModelSerializer):
    hall_name = serializers.CharField(source="hall.name", read_only=True)
    meal_display = serializers.CharField(source="get_meal_display", read_only=True)

    class Meta:
        model = MealService
        fields = [
            "id", "hall", "hall_name", "date", "meal", "meal_display",
            "registered_strength", "prep_mode", "attendance_count",
            "opens_at", "closes_at", "notes",
        ]


class AttendanceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceRecord
        fields = [
            "id", "client_uuid", "service", "student", "student_identifier",
            "method", "captured_at", "device_id", "captured_offline", "synced_at",
        ]
        read_only_fields = ["id", "synced_at"]


class AttendanceSyncItemSerializer(serializers.Serializer):
    """One scan arriving from the tablet, online or from the offline queue."""

    client_uuid = serializers.UUIDField(help_text="Client-generated id; the server ignores one it already holds.")
    service_id = serializers.IntegerField(required=False, allow_null=True)
    hall_id = serializers.IntegerField(required=False, allow_null=True)
    date = serializers.DateField(required=False, allow_null=True)
    meal = serializers.CharField(required=False, allow_blank=True)
    student_identifier = serializers.CharField(allow_blank=True)
    method = serializers.CharField(required=False, allow_blank=True)
    captured_at = serializers.DateTimeField(required=False, allow_null=True)
    device_id = serializers.CharField(required=False, allow_blank=True)
    captured_offline = serializers.BooleanField(required=False, default=False)


class AttendanceSyncBatchSerializer(serializers.Serializer):
    records = AttendanceSyncItemSerializer(many=True)
    device_id = serializers.CharField(required=False, allow_blank=True, default="")


# ---------------------------------------------------------------------------
# Calendar & configuration
# ---------------------------------------------------------------------------

class CalendarEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalendarEvent
        fields = [
            "id", "name", "event_type", "start_date", "end_date", "impact_factor",
            "affects_meals", "affects_halls", "description", "is_active",
        ]


class ServiceLevelConfigSerializer(serializers.ModelSerializer):
    hall_code = serializers.CharField(source="hall.code", read_only=True, default=None)

    class Meta:
        model = ServiceLevelConfig
        fields = [
            "id", "hall", "hall_code", "meal", "acceptable_overprep_pct",
            "max_overprep_pct", "min_buffer_portions", "effective_from", "notes",
        ]


# ---------------------------------------------------------------------------
# Forecasting
# ---------------------------------------------------------------------------

class ForecastSerializer(serializers.ModelSerializer):
    service_date = serializers.DateField(source="service.date", read_only=True)
    hall_name = serializers.CharField(source="service.hall.name", read_only=True)
    meal = serializers.CharField(source="service.meal", read_only=True)
    actual_attendance = serializers.IntegerField(source="service.attendance_count", read_only=True)
    absolute_percentage_error = serializers.SerializerMethodField()

    class Meta:
        model = Forecast
        fields = [
            "id", "service", "service_date", "hall_name", "meal",
            "method", "model_version", "generated_at", "horizon_days",
            "predicted_attendance", "lower_bound", "upper_bound", "confidence_level",
            "base_level", "weekday_factor", "event_factor", "trend_pct",
            "rmse", "mape", "input_signature", "explanation", "is_fallback",
            "observations_used", "actual_attendance", "absolute_percentage_error",
        ]

    def get_absolute_percentage_error(self, obj) -> str | None:
        value = obj.absolute_percentage_error()
        return str(value) if value is not None else None


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

class PreparationLineSerializer(serializers.ModelSerializer):
    dish_name = serializers.CharField(source="dish.name", read_only=True)

    class Meta:
        model = PreparationLine
        fields = ["id", "dish", "dish_name", "portions", "expected_share", "estimated_cost", "notes"]


class PreparationPlanSerializer(serializers.ModelSerializer):
    lines = PreparationLineSerializer(many=True, read_only=True)
    hall_name = serializers.CharField(source="service.hall.name", read_only=True)
    service_date = serializers.DateField(source="service.date", read_only=True)
    meal = serializers.CharField(source="service.meal", read_only=True)

    class Meta:
        model = PreparationPlan
        fields = [
            "id", "service", "hall_name", "service_date", "meal", "forecast",
            "generated_at", "status", "attendance_target", "safety_margin_pct",
            "portions_to_prepare", "over_preparation_pct", "estimated_cost",
            "guidance_text", "notes", "lines",
        ]


class IndentLineSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    ingredient_code = serializers.CharField(source="ingredient.code", read_only=True)
    packs = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = IndentLine
        fields = [
            "id", "ingredient", "ingredient_name", "ingredient_code", "quantity",
            "unit", "unit_cost", "estimated_cost", "source_dishes", "packs",
        ]


class IngredientIndentSerializer(serializers.ModelSerializer):
    lines = IndentLineSerializer(many=True, read_only=True)
    hall_name = serializers.CharField(source="hall.name", read_only=True)

    class Meta:
        model = IngredientIndent
        fields = [
            "id", "plan", "hall", "hall_name", "date", "generated_at",
            "total_estimated_cost", "line_count", "procurement_text", "lines",
        ]


# ---------------------------------------------------------------------------
# Actuals & waste
# ---------------------------------------------------------------------------

class DishActualSerializer(serializers.ModelSerializer):
    dish_name = serializers.CharField(source="dish.name", read_only=True)

    class Meta:
        model = DishActual
        fields = [
            "id", "dish", "dish_name", "prepared_portions", "served_portions",
            "leftover_portions", "notes",
        ]


class ServiceActualSerializer(serializers.ModelSerializer):
    dish_actuals = DishActualSerializer(many=True, read_only=True)
    hall_name = serializers.CharField(source="service.hall.name", read_only=True)
    service_date = serializers.DateField(source="service.date", read_only=True)
    meal = serializers.CharField(source="service.meal", read_only=True)
    waste_cost = serializers.SerializerMethodField()

    class Meta:
        model = ServiceActual
        fields = [
            "id", "service", "hall_name", "service_date", "meal", "recorded_by",
            "recorded_at", "prepared_portions_total", "served_portions_total",
            "leftover_portions_total", "prep_mode", "attendance_actual", "notes",
            "dish_actuals", "waste_cost",
        ]

    def get_waste_cost(self, obj) -> str:
        total = sum((w.waste_cost for w in obj.waste_records.all()), Decimal("0"))
        return str(total)


class WasteRecordSerializer(serializers.ModelSerializer):
    dish_name = serializers.CharField(source="dish.name", read_only=True)
    hall_name = serializers.CharField(source="hall.name", read_only=True)
    service_date = serializers.DateField(source="service.date", read_only=True)

    class Meta:
        model = WasteRecord
        fields = [
            "id", "service_actual", "dish", "dish_name", "service", "service_date",
            "hall", "hall_name", "meal", "leftover_portions", "waste_quantity",
            "unit", "cost_per_portion", "waste_cost", "forecast_portions",
            "over_prepared_portions", "cause", "computed_at", "notes",
        ]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id", "kind", "channel", "recipient", "role_target", "hall", "service",
            "subject", "body", "status", "sent_at", "created_at", "meta",
        ]
        read_only_fields = ["id", "created_at", "status", "sent_at"]
