from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard_home, name="dashboard-home"),
    path("student/", views.student_dashboard, name="dashboard-student"),
    path("student/menu/", views.student_menu, name="dashboard-student-menu"),
    path("finance/", views.finance_dashboard, name="dashboard-finance"),
    path("waste/", views.dashboard_waste, name="dashboard-waste"),
    path("accuracy/", views.dashboard_accuracy, name="dashboard-accuracy"),
    path("planning/", views.dashboard_planning, name="dashboard-planning"),
    path("data-quality/", views.data_quality_monitor, name="dashboard-data-quality"),
    path("export/indent/<int:plan_id>.csv", views.export_indent_csv, name="export-indent"),
]
