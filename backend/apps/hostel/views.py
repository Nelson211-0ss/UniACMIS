from __future__ import annotations

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.exceptions import error_envelope
from apps.core.permissions import HasModulePermission, IsAuthenticatedAndActive
from apps.hostel import services
from apps.hostel.models import Allocation, Room
from apps.hostel.serializers import (
    AllocateSerializer,
    AllocationSerializer,
    RoomSerializer,
    VacateSerializer,
)

UNSCOPED_ROLES = {"hostel", "ict_admin", "management"}


class RoomViewSet(viewsets.ModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "hostel.view_room",
        "POST": "hostel.add_room",
        "PUT": "hostel.change_room",
        "PATCH": "hostel.change_room",
    }
    filterset_fields = ["building", "gender_restriction", "is_active"]

    def perform_create(self, serializer) -> None:
        serializer.instance = services.create_room(
            actor=self.request.user, **serializer.validated_data
        )

    def perform_update(self, serializer) -> None:
        serializer.instance = services.update_room(
            serializer.instance, actor=self.request.user, **serializer.validated_data
        )


class AllocationViewSet(viewsets.ReadOnlyModelViewSet):
    """A student sees only their own allocation — the same self-service
    shape as `library.LoanViewSet`. Allocating and vacating are the actual
    controls, each its own permission."""

    queryset = Allocation.objects.select_related("student", "room", "academic_year")
    serializer_class = AllocationSerializer
    permission_classes = [HasModulePermission]
    required_permission = None
    filterset_fields = ["room", "academic_year", "status"]
    ordering = ["-allocated_at"]

    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_superuser or user.has_role(*UNSCOPED_ROLES):
            return queryset
        profile = getattr(user, "student_profile", None)
        if profile is not None:
            return queryset.filter(student_id=profile.pk)
        return queryset.none()

    @extend_schema(
        summary="Allocate a room to a student",
        request=AllocateSerializer,
        responses={201: AllocationSerializer},
    )
    @action(detail=False, methods=["post"])
    def allocate(self, request: Request) -> Response:
        if not request.user.has_perm("hostel.add_allocation"):
            return Response(
                error_envelope("permission_denied", "You may not allocate rooms."), status=403
            )
        serializer = AllocateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        allocation = services.allocate_room(
            student_id=data["student"],
            room_id=data["room"],
            academic_year_id=data["academic_year"],
            actor=request.user,
        )
        return Response(AllocationSerializer(allocation).data, status=201)

    @extend_schema(
        summary="Vacate a room allocation",
        request=VacateSerializer,
        responses={200: AllocationSerializer},
    )
    @action(detail=True, methods=["post"])
    def vacate(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("hostel.change_allocation"):
            return Response(
                error_envelope("permission_denied", "You may not vacate rooms."), status=403
            )
        serializer = VacateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        allocation = services.vacate_allocation(
            self.get_object(),
            actor=request.user,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(AllocationSerializer(allocation).data)

    def get_permissions(self):  # type: ignore[override]
        if self.action in {"allocate", "vacate"}:
            return [IsAuthenticatedAndActive()]
        return super().get_permissions()
