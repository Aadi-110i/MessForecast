"""Admin configuration for all models"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from core.models import User, DiningHall, MealService, CostRate, SystemConfiguration


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'role', 'dining_hall', 'is_active']
    list_filter = ['role', 'is_active', 'dining_hall']
    search_fields = ['username', 'email', 'student_id', 'first_name', 'last_name']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Mess Info', {
            'fields': ('role', 'student_id', 'phone', 'dining_hall', 'rfid_uid', 
                       'mess_category', 'is_active_student')
        }),
    )


@admin.register(DiningHall)
class DiningHallAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'capacity', 'registered_strength', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'code']


@admin.register(MealService)
class MealServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'meal_type', 'dining_hall', 'start_time', 'end_time', 
                    'safety_margin', 'is_active']
    list_filter = ['meal_type', 'dining_hall', 'is_active']


@admin.register(CostRate)
class CostRateAdmin(admin.ModelAdmin):
    list_display = ['unit', 'cost_per_unit', 'effective_from', 'effective_to']


@admin.register(SystemConfiguration)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ['key', 'value', 'updated_at']
    search_fields = ['key']
