"""REST API views.

Endpoint groups follow the specification: ``/menus``, ``/attendance``,
``/forecasts``, ``/preparation-plans``, ``/actuals`` and ``/analytics/waste``,
plus the master data the kitchen maintains.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.actuals.models import DishActual, ServiceActual
from apps.attendance.models import AttendanceRecord, MealService
from apps.attendance.services import sync_attendance_batch
from apps.catalog.models import CostRate, DiningHall, Dish, Ingredient, Recipe
from apps.core.utils import csv_response
from apps.events.models import CalendarEvent, ServiceLevelConfig
from apps.forecasting.models import Forecast
from apps.forecasting.services import forecast_service, generate_forecasts_for_range
from apps.menu.models import Menu, MenuItem, MenuSchedule
from apps.notifications.models import Notification
from apps.planning.models import IngredientIndent, PreparationPlan
from apps.planning.services import generate_preparation_plan, indent_csv_rows
from apps.reporting import services as reporting
from apps.waste.models import WasteRecord
from apps.waste.services import compute_waste_for_actual

from .permissions import HasCapability
from .serializers import (
    AttendanceRecordSerializer,
    AttendanceSyncBatchSerializer,
    CalendarEventSerializer,
    CostRateSerializer,
    DiningHallSerializer,
    DishActualSerializer,
    DishSerializer,
    ForecastSerializer,
    IngredientIndentSerializer,
    IngredientSerializer,
    MealServiceSerializer,
    MenuItemSerializer,
    MenuScheduleSerializer,
    MenuSerializer,
    NotificationSerializer,
    PreparationPlanSerializer,
    RecipeSerializer,
    ServiceActualSerializer,
    ServiceLevelConfigSerializer,
    WasteRecordSerializer,
)


class _ScopedViewSet(viewsets.ModelViewSet):
    """Common filtering helpers for the read/write capability split.

    Every viewset inherits the capability check. Without this the DRF
    default (``IsAuthenticated``) would apply and the role table in
    ``apps.accounts.permissions`` would never be consulted.
    """

    permission_classes = [HasCapability]

    def get_queryset(self):
        return super().get_queryset()


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

class DiningHallViewSet(_ScopedViewSet):
    queryset = DiningHall.objects.all()
    serializer_class = DiningHallSerializer
    capability = "MANAGE_HALLS"
    read_capability = "VIEW_MENU"
    filterset_fields = ["is_active", "code"]


class IngredientViewSet(_ScopedViewSet):
    queryset = Ingredient.objects.all()
    serializer_class = IngredientSerializer
    capability = "MANAGE_MASTERS"
    read_capability = "VIEW_MENU"
    filterset_fields = ["is_active", "category", "base_unit"]
    search_fields = ["name", "code"]


class DishViewSet(_ScopedViewSet):
    queryset = Dish.objects.all()
    serializer_class = DishSerializer
    capability = "MANAGE_MASTERS"
    read_capability = "VIEW_MENU"
    filterset_fields = ["is_active", "category"]
    search_fields = ["name", "code"]


class RecipeViewSet(_ScopedViewSet):
    queryset = Recipe.objects.all().select_related("dish")
    serializer_class = RecipeSerializer
    capability = "MANAGE_MASTERS"
    read_capability = "VIEW_MENU"
    filterset_fields = ["dish", "is_active"]


class CostRateViewSet(_ScopedViewSet):
    queryset = CostRate.objects.all().select_related("ingredient", "hall")
    serializer_class = CostRateSerializer
    capability = "MANAGE_MASTERS"
    read_capability = "VIEW_WASTE_COST"
    filterset_fields = ["ingredient", "hall"]


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

class MenuViewSet(_ScopedViewSet):
    queryset = Menu.objects.all().prefetch_related("items__dish")
    serializer_class = MenuSerializer
    capability = "PLAN_MENU"
    read_capability = "VIEW_MENU"
    filterset_fields = ["is_active"]
    search_fields = ["name", "code"]


class MenuItemViewSet(_ScopedViewSet):
    queryset = MenuItem.objects.all().select_related("dish", "menu")
    serializer_class = MenuItemSerializer
    capability = "PLAN_MENU"
    read_capability = "VIEW_MENU"
    filterset_fields = ["menu", "meal", "dish"]


class MenuScheduleViewSet(_ScopedViewSet):
    queryset = MenuSchedule.objects.all().select_related("menu", "hall")
    serializer_class = MenuScheduleSerializer
    capability = "PLAN_MENU"
    read_capability = "VIEW_MENU"
    filterset_fields = ["hall", "date", "meal", "menu", "is_published"]

    def get_queryset(self):
        queryset = super().get_queryset()
        start = self.request.query_params.get("start")
        end = self.request.query_params.get("end")
        if start:
            queryset = queryset.filter(date__gte=start)
        if end:
            queryset = queryset.filter(date__lte=end)
        return queryset


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

class MealServiceViewSet(_ScopedViewSet):
    queryset = MealService.objects.all().select_related("hall")
    serializer_class = MealServiceSerializer
    capability = "RECORD_ATTENDANCE"
    read_capability = "VIEW_FORECAST"
    filterset_fields = ["hall", "date", "meal", "prep_mode"]

    def get_queryset(self):
        queryset = super().get_queryset()
        start = self.request.query_params.get("start")
        end = self.request.query_params.get("end")
        if start:
            queryset = queryset.filter(date__gte=start)
        if end:
            queryset = queryset.filter(date__lte=end)
        return queryset


class AttendanceRecordViewSet(_ScopedViewSet):
    queryset = AttendanceRecord.objects.all().select_related("service", "hall")
    serializer_class = AttendanceRecordSerializer
    capability = "RECORD_ATTENDANCE"
    read_capability = "RECORD_ATTENDANCE"
    filterset_fields = ["service", "method", "captured_offline", "hall", "meal"]

    def get_queryset(self):
        queryset = super().get_queryset()
        student = self.request.query_params.get("student_identifier")
        if student:
            queryset = queryset.filter(student_identifier=student)
        return queryset


class AttendanceSyncView(APIView):
    """POST a batch of scans - the endpoint the offline queue drains into.

    Idempotent by construction: a ``client_uuid`` the server already holds is
    ignored, and the response says how many were new and how many duplicates
    were dropped.
    """

    capability = "RECORD_ATTENDANCE"
    permission_classes = [HasCapability]

    def post(self, request):
        serializer = AttendanceSyncBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        records = serializer.validated_data["records"]
        device_id = serializer.validated_data.get("device_id") or request.headers.get("X-Device-Id", "")
        result = sync_attendance_batch(
            [{"client_uuid": str(r["client_uuid"]), **{k: v for k, v in r.items() if k != "client_uuid"}}
             for r in records],
            device_id=device_id,
        )
        return Response(result, status=status.HTTP_200_OK)


class AttendanceCountView(APIView):
    """Live attendance count for a service - the scan screen polls this."""

    capability = "RECORD_ATTENDANCE"
    permission_classes = [HasCapability]

    def get(self, request):
        service_id = request.query_params.get("service")
        if not service_id:
            return Response({"detail": "service query parameter is required"}, status=status.HTTP_400_BAD_REQUEST)
        service = get_object_or_404(MealService.objects.select_related("hall"), pk=service_id)
        return Response(
            {
                "service": service.id,
                "hall": service.hall.name,
                "date": service.date,
                "meal": service.meal,
                "attendance_count": service.attendance_count,
                "registered_strength": service.registered_strength,
            }
        )


# ---------------------------------------------------------------------------
# Calendar & configuration
# ---------------------------------------------------------------------------

class CalendarEventViewSet(_ScopedViewSet):
    queryset = CalendarEvent.objects.all().prefetch_related("affects_halls")
    serializer_class = CalendarEventSerializer
    capability = "PLAN_MENU"
    read_capability = "VIEW_MENU"
    filterset_fields = ["event_type", "is_active"]

    def get_queryset(self):
        queryset = super().get_queryset()
        start = self.request.query_params.get("start")
        end = self.request.query_params.get("end")
        if start:
            queryset = queryset.filter(end_date__gte=start)
        if end:
            queryset = queryset.filter(start_date__lte=end)
        return queryset


class ServiceLevelConfigViewSet(_ScopedViewSet):
    queryset = ServiceLevelConfig.objects.all().select_related("hall")
    serializer_class = ServiceLevelConfigSerializer
    capability = "CONFIGURE_SERVICE_LEVEL"
    read_capability = "VIEW_FORECAST"
    filterset_fields = ["hall", "meal"]


# ---------------------------------------------------------------------------
# Forecasting
# ---------------------------------------------------------------------------

class ForecastViewSet(_ScopedViewSet):
    queryset = Forecast.objects.all().select_related("service", "service__hall")
    serializer_class = ForecastSerializer
    capability = "CONFIGURE_FORECAST"
    read_capability = "VIEW_FORECAST"
    filterset_fields = ["is_fallback", "model_version"]
    #: Running the forecast is a mess manager's job; changing the model's
    #: configuration is the administrator's.
    action_capabilities = {"generate": "PLAN_MENU", "refresh": "PLAN_MENU"}

    def get_queryset(self):
        queryset = super().get_queryset()
        start = self.request.query_params.get("start")
        end = self.request.query_params.get("end")
        if start:
            queryset = queryset.filter(service__date__gte=start)
        if end:
            queryset = queryset.filter(service__date__lte=end)
        hall = self.request.query_params.get("hall")
        if hall:
            queryset = queryset.filter(service__hall_id=hall)
        return queryset

    @action(detail=False, methods=["post"], url_path="generate")
    def generate(self, request):
        """Produce forecasts for a date range (the daily job)."""
        start = _parse_date(request.data.get("start"), "start") or timezone.localdate()
        end = _parse_date(request.data.get("end"), "end") or (start + dt.timedelta(days=7))
        results = generate_forecasts_for_range(start, end)
        return Response(
            {
                "forecasts": len(results),
                "start": start.isoformat(),
                "end": end.isoformat(),
            }
        )

    @action(detail=True, methods=["post"], url_path="refresh")
    def refresh(self, request, pk=None):
        forecast = self.get_object()
        result = forecast_service(forecast.service)
        return Response(ForecastSerializer(forecast.service.forecast).data)


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

class PreparationPlanViewSet(_ScopedViewSet):
    queryset = PreparationPlan.objects.all().select_related("service", "service__hall")
    serializer_class = PreparationPlanSerializer
    capability = "CONFIGURE_SERVICE_LEVEL"
    read_capability = "VIEW_PREPARATION_PLAN"
    filterset_fields = ["status"]

    def get_queryset(self):
        queryset = super().get_queryset()
        start = self.request.query_params.get("start")
        end = self.request.query_params.get("end")
        if start:
            queryset = queryset.filter(service__date__gte=start)
        if end:
            queryset = queryset.filter(service__date__lte=end)
        return queryset

    @action(detail=False, methods=["post"], url_path="generate")
    def generate(self, request):
        service_id = request.data.get("service")
        if not service_id:
            return Response({"detail": "service is required"}, status=status.HTTP_400_BAD_REQUEST)
        service = get_object_or_404(MealService.objects.select_related("hall"), pk=service_id)
        try:
            plan = generate_preparation_plan(service)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PreparationPlanSerializer(plan).data)

    @action(detail=True, methods=["get"], url_path="indent")
    def indent_csv(self, request, pk=None):
        """Export the ingredient indent in the procurement format."""
        plan = self.get_object()
        indent = getattr(plan, "indent", None)
        if indent is None:
            return Response({"detail": "This plan has no indent yet"}, status=status.HTTP_404_NOT_FOUND)
        header, rows = indent_csv_rows(indent)
        return csv_response(
            f"indent_{indent.hall.code}_{indent.date.isoformat()}.csv", header, rows
        )


class IngredientIndentViewSet(_ScopedViewSet):
    queryset = IngredientIndent.objects.all().select_related("hall", "plan")
    serializer_class = IngredientIndentSerializer
    capability = "CONFIGURE_SERVICE_LEVEL"
    read_capability = "VIEW_PREPARATION_PLAN"
    filterset_fields = ["hall", "date"]

    @action(detail=True, methods=["get"], url_path="export.csv")
    def export_csv(self, request, pk=None):
        indent = self.get_object()
        header, rows = indent_csv_rows(indent)
        return csv_response(
            f"indent_{indent.hall.code}_{indent.date.isoformat()}.csv", header, rows
        )


# ---------------------------------------------------------------------------
# Actuals
# ---------------------------------------------------------------------------

class ServiceActualViewSet(_ScopedViewSet):
    queryset = ServiceActual.objects.all().select_related("service", "service__hall")
    serializer_class = ServiceActualSerializer
    capability = "RECORD_ACTUALS"
    read_capability = "VIEW_WASTE_COST"
    filterset_fields = ["prep_mode"]

    def get_queryset(self):
        queryset = super().get_queryset()
        start = self.request.query_params.get("start")
        end = self.request.query_params.get("end")
        if start:
            queryset = queryset.filter(service__date__gte=start)
        if end:
            queryset = queryset.filter(service__date__lte=end)
        return queryset

    def perform_create(self, serializer):
        actual = serializer.save(recorded_by=self.request.user)
        # Cost the waste immediately: the kitchen should not have to trigger it.
        compute_waste_for_actual(actual)
        service_actual = ServiceActual.objects.get(pk=actual.pk)
        serializer.instance = service_actual

    @action(detail=True, methods=["post"], url_path="recompute-waste")
    def recompute_waste(self, request, pk=None):
        actual = self.get_object()
        records = compute_waste_for_actual(actual)
        return Response({"waste_records": len(records)})


class DishActualViewSet(_ScopedViewSet):
    queryset = DishActual.objects.all().select_related("dish", "service_actual")
    serializer_class = DishActualSerializer
    capability = "RECORD_ACTUALS"
    read_capability = "VIEW_WASTE_COST"
    filterset_fields = ["service_actual", "dish"]


# ---------------------------------------------------------------------------
# Waste & reporting
# ---------------------------------------------------------------------------

class WasteRecordViewSet(_ScopedViewSet):
    queryset = WasteRecord.objects.all().select_related("dish", "hall", "service")
    serializer_class = WasteRecordSerializer
    capability = "CONFIGURE_FORECAST"
    read_capability = "VIEW_WASTE_COST"
    filterset_fields = ["dish", "hall", "meal", "cause"]

    def get_queryset(self):
        queryset = super().get_queryset()
        start = self.request.query_params.get("start")
        end = self.request.query_params.get("end")
        if start:
            queryset = queryset.filter(service__date__gte=start)
        if end:
            queryset = queryset.filter(service__date__lte=end)
        return queryset


class NotificationViewSet(_ScopedViewSet):
    queryset = Notification.objects.all().select_related("recipient", "hall", "service")
    serializer_class = NotificationSerializer
    capability = "CONFIGURE_FORECAST"
    read_capability = "VIEW_MENU"
    filterset_fields = ["kind", "status", "channel"]

    def get_queryset(self):
        queryset = super().get_queryset()
        # A notification is addressed to someone. Only the people who manage
        # the mess see the whole outbox; everyone else sees their own.
        if self.request.user.role not in {"MESS_MANAGER", "ADMINISTRATOR", "MESS_ADMIN"}:
            queryset = queryset.filter(recipient=self.request.user)
        return queryset


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def _parse_date(value: str | None, field: str, required: bool = False) -> dt.date | None:
    """Parse an ISO date from a query parameter.

    A malformed or missing date is a client mistake, so it is reported as a
    400 rather than being allowed to raise out of the view as a 500.
    """
    if value in (None, ""):
        if required:
            raise ValidationError({field: "This date parameter is required."})
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValidationError({field: f"'{value}' is not an ISO date (YYYY-MM-DD)."})


def _date_range(request, default_days: int = 28) -> tuple[dt.date, dt.date]:
    end = _parse_date(request.query_params.get("end"), "end") or timezone.localdate()
    start = (
        _parse_date(request.query_params.get("start"), "start")
        or end - dt.timedelta(days=default_days)
    )
    return start, end


class WasteAnalyticsView(APIView):
    """``GET /api/analytics/waste`` - the waste report the specification names."""

    capability = "VIEW_WASTE_COST"
    permission_classes = [HasCapability]

    def get(self, request):
        start, end = _date_range(request)
        hall = request.query_params.get("hall")
        hall_obj = None
        if hall:
            hall_obj = get_object_or_404(DiningHall, pk=hall)

        from apps.waste import services as waste_services

        return Response(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "hall": hall_obj.name if hall_obj else "all halls",
                "totals": waste_services.waste_totals(start, end, hall_obj),
                "by_week": waste_services.waste_by_week(start, end, hall_obj),
                "by_meal": waste_services.waste_by_meal(start, end, hall_obj),
                "by_hall": waste_services.waste_by_hall(start, end),
                "top_dishes": waste_services.top_waste_dishes(start, end, hall_obj, limit=10),
            }
        )


class AccuracyAnalyticsView(APIView):
    """``GET /api/analytics/accuracy`` - MAPE by meal, hall and week."""

    capability = "VIEW_ACCURACY"
    permission_classes = [HasCapability]

    def get(self, request):
        start, end = _date_range(request)
        hall = request.query_params.get("hall")
        hall_obj = get_object_or_404(DiningHall, pk=hall) if hall else None
        return Response(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "summary": reporting.accuracy_summary(start, end, hall_obj),
                "exact_mape_pct": str(reporting.exact_mape(start, end, hall_obj)),
                "by_meal_and_hall": reporting.mape_by_meal_and_hall(start, end),
                "over_time": reporting.mape_over_time(start, end, hall_obj),
                "rows": reporting.forecast_vs_actual_rows(start, end, hall_obj, limit=200),
            }
        )


class SavingsAnalyticsView(APIView):
    """``GET /api/analytics/savings`` - the before/after comparison."""

    capability = "VIEW_ACCURACY"
    permission_classes = [HasCapability]

    def get(self, request):
        baseline_start = _parse_date(request.query_params.get("baseline_start"), "baseline_start", required=True)
        baseline_end = _parse_date(request.query_params.get("baseline_end"), "baseline_end", required=True)
        live_start = _parse_date(request.query_params.get("live_start"), "live_start", required=True)
        live_end = _parse_date(request.query_params.get("live_end"), "live_end", required=True)
        hall = request.query_params.get("hall")
        hall_obj = get_object_or_404(DiningHall, pk=hall) if hall else None

        return Response(
            {
                "baseline_start": baseline_start.isoformat(),
                "baseline_end": baseline_end.isoformat(),
                "live_start": live_start.isoformat(),
                "live_end": live_end.isoformat(),
                "comparison": reporting.baseline_comparison(
                    baseline_start, baseline_end, live_start, live_end, hall_obj
                ),
                "trend": reporting.saving_trend_by_week(
                    baseline_start, baseline_end, live_start, live_end, hall_obj
                ),
            }
        )


class DemandAnalyticsView(APIView):
    """``GET /api/analytics/demand`` - historical demand analysis (M4)."""

    capability = "VIEW_FORECAST"
    permission_classes = [HasCapability]

    def get(self, request):
        from apps.demand import services as demand_services

        start, end = _date_range(request)
        hall = request.query_params.get("hall")
        hall_obj = get_object_or_404(DiningHall, pk=hall) if hall else None
        meal = request.query_params.get("meal")

        return Response(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "summary": demand_services.attendance_summary(start, end, hall_obj),
                "by_weekday": demand_services.attendance_by_weekday(start, end, hall_obj, meal),
                "by_meal": demand_services.attendance_by_meal(start, end, hall_obj),
                "by_week": demand_services.attendance_by_week(start, end, hall_obj, meal),
                "by_period": demand_services.attendance_by_period(start, end, hall_obj),
                "dish_demand": demand_services.dish_demand(start, end, hall_obj),
            }
        )


class IngredientConsumptionView(APIView):
    """``GET /api/analytics/ingredients`` - consumption against the indent."""

    capability = "VIEW_PREPARATION_PLAN"
    permission_classes = [HasCapability]

    def get(self, request):
        start, end = _date_range(request)
        hall = request.query_params.get("hall")
        hall_obj = get_object_or_404(DiningHall, pk=hall) if hall else None
        return Response(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "rows": reporting.ingredient_consumption_vs_indent(start, end, hall_obj),
            }
        )
