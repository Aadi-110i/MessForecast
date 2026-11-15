"""Console URLs.

The administrative surfaces: menu management, recipe management, attendance,
the forecast dashboard, reports and settings. Each lives in the app that
owns the data it shows.
"""

from django.urls import path

from apps.attendance import console_views as attendance_console
from apps.catalog import views as catalog_views
from apps.forecasting import console_views as forecasting_console
from apps.menu import views as menu_views
from apps.reporting import console_views as reporting_console
from apps.reporting.design_system_views import design_system

urlpatterns = [
    # The component library, rendered.
    path("design-system/", design_system, name="design-system"),
    # Menu management.
    path("menus/", menu_views.menu_console, name="console-menus"),
    path("menus/create/", menu_views.menu_cycle_create, name="console-menu-create"),
    path("menus/<int:menu_id>/", menu_views.menu_cycle_detail, name="console-menu-detail"),
    path("menus/<int:menu_id>/items/", menu_views.menu_cycle_items, name="console-menu-items"),
    path("schedule/assign/", menu_views.menu_schedule_assign, name="console-schedule-assign"),
    path("schedule/day/", menu_views.menu_schedule_day, name="console-schedule-day"),
    path("schedule/week/", menu_views.menu_schedule_week, name="console-schedule-week"),
    path("schedule/<int:schedule_id>/publish/", menu_views.menu_schedule_publish, name="console-schedule-publish"),
    # Recipe management.
    path("recipes/", catalog_views.recipe_console, name="console-recipes"),
    path("recipes/<int:dish_id>/", catalog_views.recipe_detail, name="console-recipe-detail"),
    path("recipes/<int:dish_id>/versions/", catalog_views.recipe_create_version, name="console-recipe-version"),
    # Dish management.
    path("dishes/", catalog_views.dish_console, name="console-dishes"),
    path("dishes/new/", catalog_views.dish_create, name="console-dish-create"),
    path("dishes/<int:dish_id>/edit/", catalog_views.dish_update, name="console-dish-update"),
    path("dishes/<int:dish_id>/delete/", catalog_views.dish_delete, name="console-dish-delete"),
    # Calendar events.
    path("events/new/", reporting_console.event_create, name="console-event-create"),
    path("events/<int:event_id>/edit/", reporting_console.event_update, name="console-event-update"),
    path("events/<int:event_id>/delete/", reporting_console.event_delete, name="console-event-delete"),
    # Attendance.
    path("attendance/", attendance_console.attendance_console, name="console-attendance"),
    # Forecast.
    path("forecast/", forecasting_console.forecast_console, name="console-forecast"),
    # Reports and settings.
    path("reports/", reporting_console.reports_catalogue, name="console-reports"),
    path("settings/", reporting_console.settings_overview, name="console-settings"),
    path("export/service-ledger.csv", reporting_console.export_service_ledger_csv, name="console-export-ledger"),
    path("export/attendance.csv", reporting_console.export_attendance_csv, name="console-export-attendance"),
]
