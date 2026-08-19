"""Authentication and account management API."""

from __future__ import annotations

from contextlib import suppress

from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts import services
from apps.accounts.models import Role, UserRole
from apps.accounts.serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    MeSerializer,
    MFABackupCodesSerializer,
    MFAConfirmSerializer,
    MFADisableSerializer,
    MFASetupSerializer,
    RoleAssignmentSerializer,
    RoleSerializer,
    UserAdminSerializer,
    UserRoleSerializer,
)
from apps.core.exceptions import error_envelope
from apps.core.pagination import StandardPagination
from apps.core.permissions import HasModulePermission, IsAuthenticatedAndActive

User = get_user_model()


class LoginView(TokenObtainPairView):
    """Exchange credentials for an access and refresh token."""

    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    throttle_scope = "login"

    @extend_schema(summary="Sign in", auth=[])
    def post(self, request: Request, *args, **kwargs) -> Response:
        return super().post(request, *args, **kwargs)


class RefreshView(TokenRefreshView):
    """Exchange a refresh token for a new access token.

    Refresh tokens rotate and the old one is blacklisted, so a token copied from
    a shared campus machine stops working as soon as the real user refreshes.
    """

    permission_classes = [AllowAny]

    @extend_schema(summary="Refresh the access token", auth=[])
    def post(self, request: Request, *args, **kwargs) -> Response:
        return super().post(request, *args, **kwargs)


class LogoutView(APIView):
    """Blacklist the supplied refresh token."""

    permission_classes = [IsAuthenticatedAndActive]

    @extend_schema(summary="Sign out", request=None, responses={205: None})
    def post(self, request: Request) -> Response:
        refresh = request.data.get("refresh")
        if refresh:
            # An already-expired or already-blacklisted token still means the user
            # is signing out; failing here would only strand them on the device.
            with suppress(TokenError):
                RefreshToken(refresh).blacklist()

        services.record_logout(request.user)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(APIView):
    """The signed-in user, their roles and their effective permissions."""

    permission_classes = [HasModulePermission]
    required_permission = None  # any authenticated user may read their own identity

    @extend_schema(summary="Current user", responses={200: MeSerializer})
    def get(self, request: Request) -> Response:
        return Response(MeSerializer(request.user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticatedAndActive]

    @extend_schema(
        summary="Change your own password",
        request=ChangePasswordSerializer,
        responses={200: dict},
    )
    def post(self, request: Request) -> Response:
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password updated."})


class MFASetupView(APIView):
    """NFR-SEC-04, step 1: start enrolling an authenticator. MFA is not
    enabled until `MFAConfirmView` proves the app was actually set up."""

    permission_classes = [IsAuthenticatedAndActive]

    @extend_schema(summary="Start MFA enrolment", responses={200: MFASetupSerializer})
    def post(self, request: Request) -> Response:
        uri = services.start_mfa_enrolment(request.user)
        return Response(MFASetupSerializer({"provisioning_uri": uri}).data)


class MFAConfirmView(APIView):
    """NFR-SEC-04, step 2: the first code from the newly-added authenticator
    enables MFA and issues one-time backup codes, shown exactly once."""

    permission_classes = [IsAuthenticatedAndActive]

    @extend_schema(
        summary="Confirm MFA enrolment",
        request=MFAConfirmSerializer,
        responses={200: MFABackupCodesSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = MFAConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        codes = services.confirm_mfa_enrolment(request.user, code=serializer.validated_data["code"])
        return Response(MFABackupCodesSerializer({"backup_codes": codes}).data)


class MFADisableView(APIView):
    """Requires the current password again — a session cookie left open on a
    shared machine must not be enough on its own to weaken the account."""

    permission_classes = [IsAuthenticatedAndActive]

    @extend_schema(summary="Disable MFA", request=MFADisableSerializer, responses={200: dict})
    def post(self, request: Request) -> Response:
        serializer = MFADisableSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        services.disable_mfa(request.user)
        return Response({"detail": "MFA disabled."})


class RoleListView(APIView):
    """The roles defined by the policy."""

    permission_classes = [HasModulePermission]
    required_permission = "accounts.view_role"

    @extend_schema(summary="List roles", responses={200: RoleSerializer(many=True)})
    def get(self, request: Request) -> Response:
        roles = Role.objects.all().order_by("name")
        return Response(RoleSerializer(roles, many=True).data)


class UserViewSet(viewsets.ModelViewSet):
    """Account administration, for ICT."""

    queryset = User.objects.all().prefetch_related("role_assignments__role")
    serializer_class = UserAdminSerializer
    permission_classes = [HasModulePermission]
    pagination_class = StandardPagination
    filterset_fields = ["is_active", "is_staff", "mfa_enabled"]
    search_fields = ["email", "first_name", "middle_name", "last_name", "phone"]
    ordering = ["last_name", "first_name"]

    required_permissions = {
        "GET": "accounts.view_user",
        "POST": "accounts.add_user",
        "PUT": "accounts.change_user",
        "PATCH": "accounts.change_user",
        "DELETE": "accounts.delete_user",
    }

    def perform_create(self, serializer) -> None:
        # Staff-created accounts always start with a forced password change: the
        # initial password is necessarily known to whoever typed it in.
        serializer.save(must_change_password=True)

    @extend_schema(
        summary="Grant a role",
        request=RoleAssignmentSerializer,
        responses={200: UserRoleSerializer},
    )
    @action(detail=True, methods=["post"], url_path="grant-role")
    def grant_role(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("accounts.add_userrole"):
            return Response(
                error_envelope("permission_denied", "You may not change role assignments."),
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RoleAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        assignment = services.grant_role(
            self.get_object(),
            serializer.validated_data["role_code"],
            granted_by=request.user,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(UserRoleSerializer(assignment).data)

    @extend_schema(
        summary="Revoke a role",
        request=RoleAssignmentSerializer,
        responses={204: None},
    )
    @action(detail=True, methods=["post"], url_path="revoke-role")
    def revoke_role(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("accounts.change_userrole"):
            return Response(
                error_envelope("permission_denied", "You may not change role assignments."),
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RoleAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        services.revoke_role(
            self.get_object(),
            serializer.validated_data["role_code"],
            revoked_by=request.user,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(summary="Role history", responses={200: UserRoleSerializer(many=True)})
    @action(detail=True, methods=["get"], url_path="role-history")
    def role_history(self, request: Request, pk: str | None = None) -> Response:
        assignments = (
            UserRole.objects.filter(user=self.get_object())
            .select_related("role", "granted_by")
            .order_by("-granted_at")
        )
        return Response(UserRoleSerializer(assignments, many=True).data)
