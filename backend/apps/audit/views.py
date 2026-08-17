"""Read-only audit API. There is no write endpoint by design."""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditLog
from apps.audit.serializers import AuditLogSerializer, ChainVerificationSerializer
from apps.audit.services import verify_chain
from apps.core.pagination import AppendOnlyCursorPagination
from apps.core.permissions import HasModulePermission


class AuditLogListView(ListAPIView):
    """Search the trail.

    Cursor-paginated: this table grows without bound and a COUNT(*) over it would
    dominate the response time.
    """

    serializer_class = AuditLogSerializer
    permission_classes = [HasModulePermission]
    required_permission = "audit.view_auditlog"
    pagination_class = AppendOnlyCursorPagination
    filterset_fields = ["action", "actor", "actor_role", "request_id"]
    search_fields = ["object_repr", "field_name", "actor_name", "reason"]

    @extend_schema(
        summary="Search the audit trail",
        parameters=[
            OpenApiParameter(
                "entity",
                description="Filter by `app_label.model`, e.g. `registry.student`.",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                "object_id",
                description="Filter to one record; use together with `entity`.",
                required=False,
                type=str,
            ),
        ],
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = AuditLog.objects.select_related("actor", "content_type")

        entity = self.request.query_params.get("entity")
        if entity and "." in entity:
            app_label, model = entity.split(".", 1)
            content_type = ContentType.objects.filter(
                app_label=app_label, model=model.lower()
            ).first()
            # An unknown entity returns nothing rather than everything: silently
            # ignoring a filter on an audit search is how people draw the wrong
            # conclusion from a screenful of unrelated rows.
            queryset = (
                queryset.filter(content_type=content_type) if content_type else queryset.none()
            )

        object_id = self.request.query_params.get("object_id")
        if object_id:
            queryset = queryset.filter(object_id=str(object_id))

        return queryset


class AuditChainVerificationView(APIView):
    """Verify the hash chain over the API, for a compliance dashboard."""

    permission_classes = [HasModulePermission]
    required_permission = "audit.view_auditlog"

    @extend_schema(
        summary="Verify the audit hash chain",
        responses={200: ChainVerificationSerializer},
    )
    def get(self, request: Request) -> Response:
        limit = request.query_params.get("limit")
        result = verify_chain(limit=int(limit) if limit and limit.isdigit() else None)
        return Response(ChainVerificationSerializer(result).data)
