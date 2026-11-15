"""API URL configuration.

The specification names these resources: ``/menus``, ``/attendance``,
``/forecasts``, ``/preparation-plans``, ``/actuals`` and ``/analytics/waste``.
The rest are the master data the kitchen maintains.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("halls", views.DiningHallViewSet, basename="hall")
router.register("ingredients", views.IngredientViewSet, basename="ingredient")
router.register("dishes", views.DishViewSet, basename="dish")
router.register("recipes", views.RecipeViewSet, basename="recipe")
router.register("cost-rates", views.CostRateViewSet, basename="costrate")
router.register("menus", views.MenuViewSet, basename="menu")
router.register("menu-items", views.MenuItemViewSet, basename="menuitem")
router.register("menu-schedules", views.MenuScheduleViewSet, basename="menuschedule")
router.register("services", views.MealServiceViewSet, basename="mealservice")
router.register("attendance", views.AttendanceRecordViewSet, basename="attendance")
router.register("events", views.CalendarEventViewSet, basename="event")
router.register("service-levels", views.ServiceLevelConfigViewSet, basename="servicelevel")
router.register("forecasts", views.ForecastViewSet, basename="forecast")
router.register("preparation-plans", views.PreparationPlanViewSet, basename="preparationplan")
router.register("indents", views.IngredientIndentViewSet, basename="indent")
router.register("actuals", views.ServiceActualViewSet, basename="actual")
router.register("dish-actuals", views.DishActualViewSet, basename="dishactual")
router.register("waste", views.WasteRecordViewSet, basename="waste")
router.register("notifications", views.NotificationViewSet, basename="notification")

urlpatterns = [
    # Sync and live count sit under /attendance as the specification expects.
    path("attendance/sync", views.AttendanceSyncView.as_view(), name="attendance-sync"),
    path("attendance/count", views.AttendanceCountView.as_view(), name="attendance-count"),
    path("analytics/waste", views.WasteAnalyticsView.as_view(), name="analytics-waste"),
    path("analytics/accuracy", views.AccuracyAnalyticsView.as_view(), name="analytics-accuracy"),
    path("analytics/savings", views.SavingsAnalyticsView.as_view(), name="analytics-savings"),
    path("analytics/demand", views.DemandAnalyticsView.as_view(), name="analytics-demand"),
    path("analytics/ingredients", views.IngredientConsumptionView.as_view(), name="analytics-ingredients"),
    path("", include(router.urls)),
]
