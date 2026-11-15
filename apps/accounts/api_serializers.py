"""Serializers for the authentication and account API.

The User model is the single source of truth for a person's role and
capabilities; nothing here lets a user promote themselves.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import update_last_login
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class EmailOrUsernameTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Accept an email address or a username as the login credential."""

    default_error_messages = {
        "no_active_account": "The email/username or password is incorrect.",
    }

    def validate(self, attrs):
        credential = (attrs.get("username") or attrs.get("email") or "").strip()
        password = attrs.get("password") or ""

        if not credential or not password:
            raise serializers.ValidationError(
                {"detail": "Email/username and password are both required."}
            )

        # An email address resolves to the account's username before the
        # standard validation runs, so callers may log in with either.
        if "@" in credential:
            try:
                user = User.objects.only("username").get(email__iexact=credential)
                attrs["username"] = user.username
            except User.DoesNotExist:
                # Keep the failure generic: never reveal whether an email is
                # registered.
                attrs["username"] = credential

        data = super().validate(attrs)

        user = self.user
        data["user"] = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "name": user.get_full_name() or user.username,
            "role": user.role,
            "role_display": user.get_role_display(),
            "student_identifier": user.student_identifier,
        }
        update_last_login(None, user)
        return data


class ProfileSerializer(serializers.ModelSerializer):
    """The logged-in user's own profile. Role is read-only."""

    role = serializers.CharField(read_only=True)
    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "role_display",
            "student_identifier",
        ]
        read_only_fields = ["id", "username", "role", "student_identifier"]

    def validate_email(self, value):
        if not value:
            return value
        if User.objects.exclude(pk=self.instance.pk).filter(email__iexact=value).exists():
            raise serializers.ValidationError("That email is already in use.")
        return value


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, style={"input_type": "password"})
    new_password = serializers.CharField(required=True, style={"input_type": "password"})
    new_password_confirm = serializers.CharField(
        required=True, style={"input_type": "password"}
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def validate_old_password(self, value):
        if not self.user or not self.user.check_password(value):
            raise serializers.ValidationError("The current password is incorrect.")
        return value

    def validate_new_password(self, value):
        password_validation.validate_password(value, user=self.user)
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "The two passwords do not match."}
            )
        return attrs

    def save(self):
        self.user.set_password(self.validated_data["new_password"])
        self.user.save(update_fields=["password"])
        update_last_login(None, self.user)
        return self.user


class BlacklistRefreshTokenSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=True)

    def validate(self, attrs):
        try:
            token = RefreshToken(attrs["refresh"])
            # Blacklisting is the security boundary: a rotated token and its
            # descendants are all invalidated.
            token.blacklist()
        except TokenError as exc:
            raise InvalidToken("Token is invalid or expired.") from exc
        return attrs
