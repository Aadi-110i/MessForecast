"""Authentication and account API views.

JWT bearer tokens protect the API; session authentication keeps working for
the rendered web surfaces. Role and capabilities always come from the
database-backed User model, never from the client.
"""

from __future__ import annotations

from django.contrib.auth import update_session_auth_hash
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .api_serializers import (
    BlacklistRefreshTokenSerializer,
    ChangePasswordSerializer,
    EmailOrUsernameTokenObtainPairSerializer,
    ProfileSerializer,
)
from .permissions import CAPABILITIES


class TokenObtainPairView(TokenObtainPairView):
    """POST /api/auth/token/ - email/username and password -> access + refresh."""

    serializer_class = EmailOrUsernameTokenObtainPairSerializer
    permission_classes = [AllowAny]


class TokenRefreshView(TokenRefreshView):
    """POST /api/auth/token/refresh/ - refresh token -> new access token."""

    permission_classes = [AllowAny]


class LogoutView(APIView):
    """POST /api/auth/logout/ - blacklist the refresh token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = BlacklistRefreshTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"detail": "Logged out."}, status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """GET /api/auth/me/ - the authenticated user's profile and capabilities."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "name": user.get_full_name() or user.username,
                "role": user.role,
                "role_display": user.get_role_display(),
                "student_identifier": user.student_identifier,
                "hall": user.hall_id,
                "hall_name": user.hall.name if user.hall else None,
                "capabilities": sorted(CAPABILITIES.get(user.role, set())),
            }
        )


class ProfileView(APIView):
    """GET/PATCH /api/accounts/profile/ - view and update own profile."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = ProfileSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = ProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ChangePasswordView(APIView):
    """POST /api/accounts/change-password/ - securely change own password."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, user=request.user
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        if hasattr(request, "_request") and hasattr(request._request, "session"):
            update_session_auth_hash(request._request, user)
        return Response({"detail": "Password changed."})
