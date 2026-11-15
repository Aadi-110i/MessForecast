from django.urls import path

from . import views

urlpatterns = [
    path("", views.scan_screen, name="scan-screen"),
    path("services", views.scan_services, name="scan-services"),
    path("capture", views.capture_scan, name="scan-capture"),
    path("count", views.scan_count, name="scan-count"),
    path("student-checkin", views.student_qr_checkin, name="student-qr-checkin"),
]
