from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth import password_validation
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts import services
from apps.accounts.models import Role, User, UserRole


class LoginSerializer(TokenObtainPairSerializer):
    """Adds lockout handling, MFA and audit logging to the JWT login.

    Campus machines are shared and passwords get written on desks, so repeated
    failures lock the account rather than allowing an unlimited guessing run.
    """

    otp = serializers.CharField(required=False, allow_blank=True, write_only=True)

    @classmethod
    def get_token(cls, user: User):  # type: ignore[override]
        token = super().get_token(user)
        # Claims the PWA can read without a round trip. Authorisation is still
        # decided server-side on every request; these are for rendering only.
        token["roles"] = user.role_codes()
        token["name"] = user.get_full_name()
        token["must_change_password"] = user.must_change_password
        return token

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        email = (attrs.get("email") or "").strip().lower()

        candidate = User.objects.filter(email__iexact=email).first()
        if candidate is not None and candidate.is_locked_out:
            raise serializers.ValidationError(
                {
                    "detail": (
                        "This account is temporarily locked after repeated failed "
                        "sign-in attempts. Try again later or ask ICT to unlock it."
                    )
                },
                code="account_locked",
            )

        try:
            data = super().validate(attrs)
            if self.user.mfa_enabled and not services.verify_mfa_code(
                self.user, attrs.get("otp", "")
            ):
                raise serializers.ValidationError(
                    {"detail": "A valid multi-factor authentication code is required."},
                    code="mfa_required",
                )
        except Exception:
            services.record_failed_login(
                email,
                max_attempts=settings.LOGIN_MAX_FAILED_ATTEMPTS,
                lockout_minutes=settings.LOGIN_LOCKOUT_MINUTES,
            )
            raise

        request = self.context.get("request")
        ip = None
        if request is not None:
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
            ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")

        services.record_successful_login(self.user, ip=ip)

        data["user"] = UserSummarySerializer(self.user).data
        return data


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["code", "name", "description"]
        read_only_fields = fields


class UserSummarySerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "middle_name",
            "last_name",
            "full_name",
            "phone",
            "roles",
            "mfa_enabled",
            "must_change_password",
            "is_staff",
        ]
        read_only_fields = fields

    def get_roles(self, obj: User) -> list[str]:
        return obj.role_codes()


class MeSerializer(UserSummarySerializer):
    """`/auth/me` — identity plus what the UI may offer."""

    permissions = serializers.SerializerMethodField()

    class Meta(UserSummarySerializer.Meta):
        fields = [*UserSummarySerializer.Meta.fields, "permissions", "last_login"]
        read_only_fields = fields

    def get_permissions(self, obj: User) -> list[str]:
        return services.effective_permissions(obj)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value: str) -> str:
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value: str) -> str:
        password_validation.validate_password(value, self.context["request"].user)
        return value

    def save(self, **kwargs: Any) -> User:
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        return user


class MFASetupSerializer(serializers.Serializer):
    provisioning_uri = serializers.CharField(read_only=True)


class MFAConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(write_only=True)


class MFABackupCodesSerializer(serializers.Serializer):
    backup_codes = serializers.ListField(child=serializers.CharField(), read_only=True)


class MFADisableSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value: str) -> str:
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value


class UserRoleSerializer(serializers.ModelSerializer):
    role_code = serializers.CharField(source="role.code", read_only=True)
    granted_by_name = serializers.CharField(source="granted_by.get_full_name", read_only=True)

    class Meta:
        model = UserRole
        fields = [
            "id",
            "role_code",
            "granted_at",
            "granted_by_name",
            "revoked_at",
            "reason",
        ]
        read_only_fields = fields


class UserAdminSerializer(serializers.ModelSerializer):
    """Account management for ICT."""

    full_name = serializers.CharField(source="get_full_name", read_only=True)
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "middle_name",
            "last_name",
            "full_name",
            "phone",
            "is_active",
            "is_staff",
            "mfa_enabled",
            "must_change_password",
            "roles",
            "last_login",
            "created_at",
        ]
        read_only_fields = ["id", "full_name", "roles", "last_login", "created_at"]

    def get_roles(self, obj: User) -> list[str]:
        return obj.role_codes()


class RoleAssignmentSerializer(serializers.Serializer):
    role_code = serializers.CharField()
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)
