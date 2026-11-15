"""Account and authentication API URLs.

Mounted under ``/api/`` alongside the platform API.
"""

from django.urls import path

from . import api_views

urlpatterns = [
    path("auth/token/", api_views.TokenObtainPairView.as_view(), name="auth-token-obtain"),
    path("auth/token/refresh/", api_views.TokenRefreshView.as_view(), name="auth-token-refresh"),
    path("auth/logout/", api_views.LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", api_views.MeView.as_view(), name="auth-me"),
    path("accounts/profile/", api_views.ProfileView.as_view(), name="accounts-profile"),
    path(
        "accounts/change-password/",
        api_views.ChangePasswordView.as_view(),
        name="accounts-change-password",
    ),
]
