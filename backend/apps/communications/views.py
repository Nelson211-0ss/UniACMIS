from __future__ import annotations

from django.db.models import Q, QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.communications import services
from apps.communications.models import Announcement, AudienceType
from apps.communications.serializers import AnnouncementSerializer, SendAnnouncementSerializer
from apps.core.exceptions import error_envelope
from apps.core.permissions import HasModulePermission, IsAuthenticatedAndActive

UNSCOPED_ROLES = {"registrar", "hod", "ict_admin", "management"}


class AnnouncementViewSet(viewsets.ReadOnlyModelViewSet):
    """Not sensitive data — every announcement is meant to be read by its
    audience, so the queryset narrows who that audience *is* rather than
    hiding the announcement itself."""

    queryset = Announcement.objects.select_related("programme")
    serializer_class = AnnouncementSerializer
    permission_classes = [HasModulePermission]
    required_permission = None
    filterset_fields = ["audience_type", "programme"]
    ordering = ["-sent_at"]

    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_superuser or user.has_role(*UNSCOPED_ROLES):
            return queryset
        profile = getattr(user, "student_profile", None)
        if profile is not None:
            return queryset.filter(
                Q(audience_type=AudienceType.ALL_STUDENTS) | Q(programme_id=profile.programme_id)
            )
        return queryset.filter(audience_type=AudienceType.ALL_STUDENTS)

    @extend_schema(
        summary="Send an announcement",
        request=SendAnnouncementSerializer,
        responses={201: AnnouncementSerializer},
    )
    @action(detail=False, methods=["post"])
    def send(self, request: Request) -> Response:
        if not request.user.has_perm("communications.send_announcement"):
            return Response(
                error_envelope("permission_denied", "You may not send announcements."), status=403
            )
        serializer = SendAnnouncementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        announcement = services.send_announcement(
            title=data["title"],
            body=data["body"],
            audience_type=data["audience_type"],
            programme_id=data.get("programme"),
            actor=request.user,
        )
        return Response(AnnouncementSerializer(announcement).data, status=201)

    def get_permissions(self):  # type: ignore[override]
        if self.action == "send":
            return [IsAuthenticatedAndActive()]
        return super().get_permissions()
