"""
Main URL configuration for Mess Demand Forecasting Platform.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from rest_framework.authtoken.views import obtain_auth_token
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

schema_view = get_schema_view(
    openapi.Info(
        title="Mess Demand Forecasting API",
        default_version='v1',
        description="API for Meal Demand Forecasting and Food-Waste Reduction Platform",
        contact=openapi.Contact(email="admin@mess.edu"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API docs
    path('api/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('api/redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    
    # Auth
    path('api/auth/token/', obtain_auth_token, name='api_token_auth'),
    path('api/auth/', include('core.urls')),
    
    # App APIs
    path('api/menus/', include('menu.urls')),
    path('api/attendance/', include('attendance.urls')),
    path('api/calendar/', include('calendar_events.urls')),
    path('api/forecasts/', include('forecasting.urls')),
    path('api/preparation-plans/', include('preparation.urls')),
    path('api/actuals/', include('actuals.urls')),
    path('api/analytics/', include('analytics.urls')),
    
    # Frontend - serve SPA
    path('', TemplateView.as_view(template_name='index.html'), name='home'),
    path('<path:path>', TemplateView.as_view(template_name='index.html'), name='spa'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
