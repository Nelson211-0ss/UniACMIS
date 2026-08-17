"""
Sync API.

`POST /api/v1/sync/batch` is the endpoint the offline outbox flushes to. It
returns **200 with a per-operation status** even when some operations fail: a
device that queued ninety attendance rows and one bad one must land the ninety.
Clients therefore read `results[].status`, not just the HTTP code.

`POST /api/v1/sync/operations` is the single-operation form, which does map the
outcome onto an HTTP status — handy for simple clients and for debugging.
"""

from __future__ import annotations

from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import context, ports
from apps.core.models import ConflictResolution, SyncConflict, SyncStatus
from apps.core.pagination import StandardPagination
from apps.core.permissions import HasModulePermission
from apps.core.sync.engine import apply_batch, apply_operation
from apps.core.sync.handlers import registered_entities
from apps.core.sync.serializers import (
    ConflictResolutionSerializer,
    SyncBatchSerializer,
    SyncConflictSerializer,
    SyncOperationSerializer,
)

_STATUS_MAP = {
    SyncStatus.APPLIED: status.HTTP_201_CREATED,
    SyncStatus.DUPLICATE: status.HTTP_200_OK,
    SyncStatus.CONFLICT: status.HTTP_409_CONFLICT,
    SyncStatus.REJECTED: status.HTTP_400_BAD_REQUEST,
}


class SyncBatchView(APIView):
    """Flush a queue of offline operations."""

    permission_classes = [HasModulePermission]
    required_permission = None  # per-entity permissions are enforced per operation
    throttle_scope = "sync"

    @extend_schema(
        summary="Flush queued offline operations",
        request=SyncBatchSerializer,
        responses={200: dict},
        examples=[
            OpenApiExample(
                "Attendance queued during an outage",
                value={
                    "operations": [
                        {
                            "client_op_id": "550e8400-e29b-41d4-a716-446655440000",
                            "entity": "registry.student",
                            "action": "create",
                            "payload": {"first_name": "Aluel", "last_name": "Deng"},
                            "client_timestamp": "2026-08-17T09:14:03Z",
                            "device_id": "registry-laptop-02",
                        }
                    ]
                },
                request_only=True,
            )
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = SyncBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        results = apply_batch(serializer.to_inputs(), request.user)
        counts: dict[str, int] = {}
        for result in results:
            counts[result["status"]] = counts.get(result["status"], 0) + 1

        return Response(
            {
                "received_at": timezone.now(),
                "request_id": context.get_request_id() or "",
                "summary": counts,
                "results": results,
            },
            status=status.HTTP_200_OK,
        )


class SyncOperationView(APIView):
    """Submit a single operation, with the outcome mapped onto an HTTP status."""

    permission_classes = [HasModulePermission]
    required_permission = None
    throttle_scope = "sync"

    @extend_schema(
        summary="Submit one offline operation",
        request=SyncOperationSerializer,
        responses={201: dict, 200: dict, 409: dict, 400: dict},
    )
    def post(self, request: Request) -> Response:
        serializer = SyncOperationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        outcome = apply_operation(serializer.to_input(), request.user)
        return Response(
            outcome.as_dict(),
            status=_STATUS_MAP.get(outcome.status, status.HTTP_200_OK),
        )


class SyncEntitiesView(APIView):
    """Which entities are offline-capable, and how each resolves conflicts.

    The client uses this to decide what it may safely queue: an entity it does
    not know about must not be written offline.
    """

    permission_classes = [HasModulePermission]
    required_permission = None

    @extend_schema(summary="List sync-capable entities", responses={200: dict})
    def get(self, request: Request) -> Response:
        return Response({"entities": registered_entities()})


class SyncConflictListView(ListAPIView):
    """Conflicts awaiting human resolution."""

    serializer_class = SyncConflictSerializer
    permission_classes = [HasModulePermission]
    required_permission = "core.view_syncconflict"
    pagination_class = StandardPagination
    filterset_fields = ["status", "entity"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = SyncConflict.objects.select_related("sync_operation", "resolved_by")
        if self.request.query_params.get("status") is None:
            # Default to the ones that need action.
            queryset = queryset.filter(status=ConflictResolution.OPEN)
        return queryset


class SyncConflictResolveView(APIView):
    """Resolve a conflict: keep the server value, accept the client value, or
    dismiss it. A reason is mandatory and the decision is audited."""

    permission_classes = [HasModulePermission]
    required_permission = "core.resolve_syncconflict"

    @extend_schema(
        summary="Resolve a sync conflict",
        request=ConflictResolutionSerializer,
        responses={200: SyncConflictSerializer},
    )
    def post(self, request: Request, pk: int) -> Response:
        serializer = ConflictResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            conflict = SyncConflict.objects.get(pk=pk)
        except SyncConflict.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "not_found",
                        "message": "Conflict not found.",
                        "details": {},
                        "request_id": context.get_request_id() or "",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not conflict.is_open:
            return Response(
                {
                    "error": {
                        "code": "already_resolved",
                        "message": f"This conflict was already {conflict.get_status_display()}.",
                        "details": {},
                        "request_id": context.get_request_id() or "",
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )

        resolution = serializer.validated_data["resolution"]
        reason = serializer.validated_data["reason"]

        conflict.status = resolution
        conflict.resolution_reason = reason
        conflict.resolved_by = request.user
        conflict.resolved_at = timezone.now()
        conflict.save(update_fields=["status", "resolution_reason", "resolved_by", "resolved_at"])

        # Accepting the client value is a deliberate overwrite of stored data, so
        # it is recorded as such rather than left implicit in the conflict row.
        ports.audit().record_action(
            instance=conflict,
            action="approve",
            description=(
                f"Sync conflict on {conflict.entity}.{conflict.field_name} "
                f"resolved as {resolution}."
            ),
            reason=reason,
        )

        return Response(SyncConflictSerializer(conflict).data, status=status.HTTP_200_OK)
