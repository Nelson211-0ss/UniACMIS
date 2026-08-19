from __future__ import annotations

from rest_framework import viewsets

from apps.alumni import services
from apps.alumni.models import AlumniEvent, AlumniProfile
from apps.alumni.serializers import AlumniEventSerializer, AlumniProfileSerializer
from apps.core.permissions import HasModulePermission


class AlumniProfileViewSet(viewsets.ModelViewSet):
    queryset = AlumniProfile.objects.select_related("student")
    serializer_class = AlumniProfileSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "alumni.view_alumniprofile",
        "POST": "alumni.add_alumniprofile",
        "PUT": "alumni.change_alumniprofile",
        "PATCH": "alumni.change_alumniprofile",
    }
    filterset_fields = ["employment_status", "is_contactable"]
    search_fields = ["student__student_id", "student__last_name", "current_employer"]

    def perform_create(self, serializer) -> None:
        data = dict(serializer.validated_data)
        student_id = data.pop("student").pk
        serializer.instance = services.create_alumni_profile(
            student_id=student_id, actor=self.request.user, **data
        )

    def perform_update(self, serializer) -> None:
        data = dict(serializer.validated_data)
        data.pop("student", None)
        serializer.instance = services.update_alumni_profile(
            serializer.instance, actor=self.request.user, **data
        )


class AlumniEventViewSet(viewsets.ModelViewSet):
    queryset = AlumniEvent.objects.all()
    serializer_class = AlumniEventSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "SAFE": "alumni.view_alumnievent",
        "POST": "alumni.add_alumnievent",
        "PUT": "alumni.change_alumnievent",
        "PATCH": "alumni.change_alumnievent",
    }
    filterset_fields = ["event_date"]

    def perform_create(self, serializer) -> None:
        serializer.instance = services.create_alumni_event(
            actor=self.request.user, **serializer.validated_data
        )

    def perform_update(self, serializer) -> None:
        serializer.instance = services.update_alumni_event(
            serializer.instance, actor=self.request.user, **serializer.validated_data
        )
