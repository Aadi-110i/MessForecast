"""Menu admin"""
from django.contrib import admin
from menu.models import Ingredient, Dish, Recipe, RecipeItem, Menu, MenuDish, MenuSchedule


class RecipeItemInline(admin.TabularInline):
    model = RecipeItem
    extra = 1
    autocomplete_fields = ['ingredient']


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'category', 'unit', 'cost_per_unit', 'is_active']
    list_filter = ['category', 'unit', 'is_active']
    search_fields = ['name', 'code', 'supplier']


@admin.register(Dish)
class DishAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'category', 'is_vegetarian', 'is_vegan', 'is_active']
    list_filter = ['category', 'is_vegetarian', 'is_vegan', 'is_active']
    search_fields = ['name', 'code']


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ['dish', 'name', 'portions', 'portion_size_grams', 'is_default']
    list_filter = ['is_default', 'dish']
    inlines = [RecipeItemInline]


class MenuDishInline(admin.TabularInline):
    model = MenuDish
    extra = 2


@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    list_display = ['name', 'dining_hall', 'meal_service', 'is_published']
    list_filter = ['dining_hall', 'meal_service', 'is_published']
    inlines = [MenuDishInline]


@admin.register(MenuSchedule)
class MenuScheduleAdmin(admin.ModelAdmin):
    list_display = ['menu', 'date', 'is_active', 'expected_attendance']
    list_filter = ['is_active', 'menu__dining_hall']
    date_hierarchy = 'date'
