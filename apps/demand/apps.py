from django.apps import AppConfig


class DemandConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.demand"
    label = "demand"
    verbose_name = "Historical Demand Analysis"
