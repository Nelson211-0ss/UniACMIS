"""Read/write API for institutional configuration."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import (
    AcademicYear,
    GradeBand,
    GradingScale,
    Institution,
    Semester,
)
from apps.academics.serializers import (
    AcademicYearSerializer,
    GradeBandSerializer,
    GradingScaleSerializer,
    InstitutionSerializer,
    SemesterSerializer,
)
from apps.academics.services import calendar
from apps.core.permissions import HasModulePermission


class InstitutionViewSet(viewsets.ModelViewSet):
    queryset = Institution.objects.all()
    serializer_class = InstitutionSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "academics.view_institution",
        "POST": "academics.add_institution",
        "PUT": "academics.change_institution",
        "PATCH": "academics.change_institution",
    }
    pagination_class = None


class AcademicYearViewSet(viewsets.ModelViewSet):
    queryset = AcademicYear.objects.prefetch_related("semesters").all()
    serializer_class = AcademicYearSerializer
    permission_classes = [HasModulePermission]
    filterset_fields = ["is_current"]
    search_fields = ["name"]
    required_permissions = {
        "GET": "academics.view_academicyear",
        "POST": "academics.add_academicyear",
        "PUT": "academics.change_academicyear",
        "PATCH": "academics.change_academicyear",
        "DELETE": "academics.delete_academicyear",
    }


class SemesterViewSet(viewsets.ModelViewSet):
    queryset = Semester.objects.select_related("academic_year").all()
    serializer_class = SemesterSerializer
    permission_classes = [HasModulePermission]
    filterset_fields = ["is_current", "academic_year"]
    required_permissions = {
        "GET": "academics.view_semester",
        "POST": "academics.add_semester",
        "PUT": "academics.change_semester",
        "PATCH": "academics.change_semester",
        "DELETE": "academics.delete_semester",
    }


class GradingScaleViewSet(viewsets.ModelViewSet):
    queryset = GradingScale.objects.prefetch_related("bands").all()
    serializer_class = GradingScaleSerializer
    permission_classes = [HasModulePermission]
    filterset_fields = ["is_default", "is_locked"]
    required_permissions = {
        "GET": "academics.view_gradingscale",
        "POST": "academics.add_gradingscale",
        "PUT": "academics.change_gradingscale",
        "PATCH": "academics.change_gradingscale",
    }

    @extend_schema(summary="Is this scale's band coverage usable?", responses={200: dict})
    @action(detail=True, methods=["get"], url_path="bands-check")
    def bands_check(self, request: Request, pk: str | None = None) -> Response:
        """A misconfigured scale silently corrupts every transcript computed
        from it, so this answers "is it safe to publish results against this
        yet?" before anything depends on the answer."""
        try:
            self.get_object().validate_bands()
        except DjangoValidationError as error:
            return Response({"ok": False, "errors": list(error.messages)})
        return Response({"ok": True, "errors": []})


class GradeBandViewSet(viewsets.ModelViewSet):
    """The letter grades a scale is made of (FR-EXM-04).

    A band is edited one row at a time — a registrar adds "A: 70–100" before
    knowing what the next band will be — so the whole-scale invariant (0–100
    covered exactly, no gaps, no overlaps) is *not* enforced per write. That
    would make incremental entry impossible, the same reason
    `examinations.Assessment` validates its weight sum at result time rather
    than on each component. `GradingScale.validate_bands()` is the whole-scale
    check; `bands-check/` exposes it so a registrar can ask "is this scale
    usable yet?" before results depend on the answer.
    """

    queryset = GradeBand.objects.select_related("scale").all()
    serializer_class = GradeBandSerializer
    permission_classes = [HasModulePermission]
    filterset_fields = ["scale", "is_pass"]
    ordering = ["scale", "-min_percent"]
    required_permissions = {
        "GET": "academics.view_gradeband",
        "POST": "academics.add_gradeband",
        "PUT": "academics.change_gradeband",
        "PATCH": "academics.change_gradeband",
        "DELETE": "academics.delete_gradeband",
    }


class CalendarStatusView(APIView):
    """What the calendar currently permits.

    The PWA reads this to decide what to offer, and — importantly for an
    offline-first client — what it must refuse to queue. Queueing a registration
    while the window is shut would only produce a rejection hours later.
    """

    permission_classes = [HasModulePermission]
    required_permission = None

    @extend_schema(summary="Current academic calendar status", responses={200: dict})
    def get(self, request: Request) -> Response:
        year = calendar.current_year()
        semester = calendar.current_semester()

        return Response(
            {
                "academic_year": AcademicYearSerializer(year).data if year else None,
                "semester": SemesterSerializer(semester).data if semester else None,
                "registration_open": calendar.is_registration_open(semester),
                "add_drop_open": calendar.is_add_drop_open(semester),
                "exam_period": calendar.is_exam_period(semester),
                "configured": year is not None and semester is not None,
            }
        )
