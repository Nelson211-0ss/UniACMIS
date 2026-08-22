from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.permissions import HasModulePermission
from apps.curriculum.models import (
    Course,
    CurriculumCourse,
    CurriculumVersion,
    Department,
    Faculty,
    Prerequisite,
    Programme,
)
from apps.curriculum.serializers import (
    CourseSerializer,
    CurriculumCourseSerializer,
    CurriculumVersionSerializer,
    DepartmentSerializer,
    FacultySerializer,
    PrerequisiteSerializer,
    ProgrammeSerializer,
)
from apps.curriculum.services import curriculum_health


def _crud(model: str) -> dict[str, str]:
    return {
        "GET": f"curriculum.view_{model}",
        "POST": f"curriculum.add_{model}",
        "PUT": f"curriculum.change_{model}",
        "PATCH": f"curriculum.change_{model}",
        "DELETE": f"curriculum.delete_{model}",
    }


class FacultyViewSet(viewsets.ModelViewSet):
    queryset = Faculty.objects.select_related("dean").all()
    serializer_class = FacultySerializer
    permission_classes = [HasModulePermission]
    required_permissions = _crud("faculty")
    filterset_fields = ["is_active"]
    search_fields = ["code", "name"]


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.select_related("faculty", "head").all()
    serializer_class = DepartmentSerializer
    permission_classes = [HasModulePermission]
    required_permissions = _crud("department")
    filterset_fields = ["faculty", "is_active"]
    search_fields = ["code", "name"]


class ProgrammeViewSet(viewsets.ModelViewSet):
    queryset = Programme.objects.select_related("department", "department__faculty").all()
    serializer_class = ProgrammeSerializer
    permission_classes = [HasModulePermission]
    required_permissions = _crud("programme")
    filterset_fields = ["department", "award", "is_active"]
    search_fields = ["code", "name"]


class CourseViewSet(viewsets.ModelViewSet):
    queryset = (
        Course.objects.select_related("department")
        .prefetch_related("prerequisites__required_course")
        .all()
    )
    serializer_class = CourseSerializer
    permission_classes = [HasModulePermission]
    required_permissions = _crud("course")
    filterset_fields = ["department", "level", "is_active"]
    search_fields = ["code", "title"]


class CurriculumCourseViewSet(viewsets.ModelViewSet):
    """Which courses a curriculum version is made of, and where each sits in
    the programme's structure (FR-CUR-03).

    The rules worth failing on — a year_of_study past the programme's duration,
    an elective with no group to choose within — live in
    `CurriculumCourse.clean()`, run via `ModelCleanSerializerMixin`.
    """

    queryset = CurriculumCourse.objects.select_related(
        "course", "curriculum_version__programme"
    ).all()
    serializer_class = CurriculumCourseSerializer
    permission_classes = [HasModulePermission]
    required_permissions = _crud("curriculumcourse")
    filterset_fields = ["curriculum_version", "course", "year_of_study", "is_core"]
    ordering = ["year_of_study", "semester_sequence"]


class PrerequisiteViewSet(viewsets.ModelViewSet):
    """Course prerequisites (FR-CUR-02).

    `Prerequisite.clean()` walks the dependency graph to refuse a cycle — a
    chain that would make its own courses permanently unregisterable — and is
    run via `ModelCleanSerializerMixin`, which a plain serializer save skips.
    """

    queryset = Prerequisite.objects.select_related("course", "required_course").all()
    serializer_class = PrerequisiteSerializer
    permission_classes = [HasModulePermission]
    required_permissions = _crud("prerequisite")
    filterset_fields = ["course", "required_course"]


class CurriculumVersionViewSet(viewsets.ModelViewSet):
    queryset = (
        CurriculumVersion.objects.select_related("programme")
        .prefetch_related("courses__course")
        .all()
    )
    serializer_class = CurriculumVersionSerializer
    permission_classes = [HasModulePermission]
    required_permissions = _crud("curriculumversion")
    filterset_fields = ["programme", "status"]
    search_fields = ["version", "programme__code"]

    @extend_schema(
        summary="Configuration check for a curriculum version",
        responses={200: dict},
    )
    @action(detail=True, methods=["get"])
    def health(self, request: Request, pk: str | None = None) -> Response:
        """Flags gaps that would otherwise surface when a final-year student
        cannot graduate."""
        return Response(curriculum_health(self.get_object().pk))
