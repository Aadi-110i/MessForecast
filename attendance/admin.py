"""Attendance, Forecasting, Preparation, Actuals admin"""
from django.contrib import admin

# Attendance
from attendance.models import AttendanceRecord, AttendanceSummary, QRToken

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ['student', 'meal_service', 'date', 'scan_time', 'capture_method', 'is_valid']
    list_filter = ['capture_method', 'is_valid', 'date', 'meal_service']
    search_fields = ['student__username', 'student__student_id', 'student_id_str', 'client_uuid']
    date_hierarchy = 'date'

@admin.register(AttendanceSummary)
class AttendanceSummaryAdmin(admin.ModelAdmin):
    list_display = ['dining_hall', 'meal_service', 'date', 'valid_count', 'finalized']
    list_filter = ['finalized', 'dining_hall', 'meal_service']
    date_hierarchy = 'date'

# Calendar
from calendar_events.models import CalendarEvent

@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    list_display = ['title', 'event_type', 'start_date', 'end_date', 'impact_level', 'attendance_multiplier']
    list_filter = ['event_type', 'impact_level']
    filter_horizontal = ['affected_halls']

# Forecasting
from forecasting.models import Forecast, ForecastModel, ForecastAccuracyReport

@admin.register(ForecastModel)
class ForecastModelAdmin(admin.ModelAdmin):
    list_display = ['name', 'method', 'is_active', 'current_mape', 'lookback_days']
    list_filter = ['method', 'is_active']

@admin.register(Forecast)
class ForecastAdmin(admin.ModelAdmin):
    list_display = ['dining_hall', 'meal_service', 'date', 'predicted_attendance', 
                    'actual_attendance', 'mape', 'status']
    list_filter = ['status', 'dining_hall', 'meal_service', 'is_holiday']
    date_hierarchy = 'date'

# Preparation
from preparation.models import PreparationPlan, IngredientIndent, IndentItem

class PreparationDishInline(admin.TabularInline):
    from preparation.models import PreparationDish
    model = PreparationDish
    extra = 0

@admin.register(PreparationPlan)
class PreparationPlanAdmin(admin.ModelAdmin):
    list_display = ['forecast', 'planned_portions', 'safety_margin_used', 'status']
    list_filter = ['status']

class IndentItemInline(admin.TabularInline):
    model = IndentItem
    extra = 0

@admin.register(IngredientIndent)
class IngredientIndentAdmin(admin.ModelAdmin):
    list_display = ['reference_number', 'date_required', 'status', 'total_estimated_cost']
    list_filter = ['status']
    inlines = [IndentItemInline]

# Actuals
from actuals.models import ServiceActual, DishActual, WasteRecord

class DishActualInline(admin.TabularInline):
    model = DishActual
    extra = 0

@admin.register(ServiceActual)
class ServiceActualAdmin(admin.ModelAdmin):
    list_display = ['dining_hall', 'meal_service', 'date', 'actual_attendance', 'is_finalized']
    list_filter = ['is_finalized', 'dining_hall', 'meal_service']
    date_hierarchy = 'date'
    inlines = [DishActualInline]

@admin.register(WasteRecord)
class WasteRecordAdmin(admin.ModelAdmin):
    list_display = ['dish', 'dining_hall', 'meal_service', 'date', 'portions_wasted', 'total_waste_cost']
    list_filter = ['dining_hall', 'meal_service', 'dish']
    date_hierarchy = 'date'
