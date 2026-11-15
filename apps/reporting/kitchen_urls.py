from django.urls import path

from . import views

urlpatterns = [
    # The tablet home: today's services and what each one still needs.
    path("", views.kitchen_dashboard, name="kitchen-dashboard"),
    # The old name for the same place, kept so existing links keep working.
    path("", views.kitchen_dashboard, name="kitchen-screen"),
    # Writing up one service.
    path("actuals/<int:service_id>/", views.kitchen_actuals, name="kitchen-actuals"),
    # The preparation brief for one service, as JSON for the kitchen screen.
    path("guidance/<int:service_id>", views.kitchen_guidance, name="kitchen-guidance"),
]
