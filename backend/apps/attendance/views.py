from __future__ import annotations

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.mixins import ScopedQuerysetMixin
from apps.attendance import services
from apps.attendance.models import SessionRecord
from apps.attendance.serializers import (
    ExamEligibilitySerializer,
    GrantWaiverSerializer,
    RecordSessionSerializer,
    SessionRecordSerializer,
)
from apps.core.exceptions import error_envelope
from apps.core.permissions import HasModulePermission

# Roles that may read or waive any registration's attendance, not only rows
# their own scope already exposes — the examinations office needs this to
# decide exam eligibility (FR-ATT-02) without also being a "sees every row"
# role for browsing the register itself.
ELIGIBILITY_ROLES = {"registrar", "ict_admin", "management", "examinations"}
UNSCOPED_ROLES = {"registrar", "ict_admin", "management"}


class SessionRecordViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    """Browsing the register. Marking it happens through `record`, below —
    a plain PATCH on one row would let a status change skip the roster
    validation `record_session` performs against the course's active
    registrations."""

    queryset = SessionRecord.objects.select_related(
        "registration__student", "timetable_entry__course", "timetable_entry__lecturer__user"
    )
    serializer_class = SessionRecordSerializer
    permission_classes = [HasModulePermission]
    required_permission = "attendance.view_sessionrecord"
    filterset_fields = ["timetable_entry", "session_date", "status", "registration"]
    ordering = ["-session_date"]

    unscoped_roles = {"registrar", "ict_admin", "management"}
    scope_methods = {
        "student": "scope_to_self",
        "lecturer": "scope_to_own_classes",
        "hod": "scope_to_department",
    }

    def scope_to_self(self, queryset: QuerySet, user) -> QuerySet:
        return queryset.filter(registration__student__user=user)

    def scope_to_own_classes(self, queryset: QuerySet, user) -> QuerySet:
        return queryset.filter(timetable_entry__lecturer__user=user)

    def scope_to_department(self, queryset: QuerySet, user) -> QuerySet:
        profile = getattr(user, "staff_profile", None)
        if profile is None or profile.department_id is None:
            return queryset.none()
        return queryset.filter(timetable_entry__course__department_id=profile.department_id)

    @extend_schema(
        summary="Record or correct a session's register",
        request=RecordSessionSerializer,
        responses={200: SessionRecordSerializer(many=True)},
    )
    @action(detail=False, methods=["post"])
    def record(self, request: Request) -> Response:
        if not request.user.has_perm("attendance.add_sessionrecord"):
            return Response(
                error_envelope("permission_denied", "You may not record attendance."), status=403
            )
        serializer = RecordSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        records = services.record_session(
            timetable_entry_id=data["timetable_entry"],
            session_date=data["session_date"],
            marks=data["marks"],
            actor=request.user,
        )
        return Response(SessionRecordSerializer(records, many=True).data)


class AttendanceSummaryView(APIView):
    """A registration's own attendance percentage — the number a class
    register screen shows live, and the same figure `exam_eligibility` below
    decides on."""

    permission_classes = [HasModulePermission]
    required_permission = "attendance.view_sessionrecord"

    def get(self, request: Request, registration_id: int) -> Response:
        if not _may_view(request, registration_id):
            return Response(
                error_envelope("permission_denied", "You may not view this record."), status=403
            )
        summary = services.attendance_summary(registration_id)
        return Response(
            {
                "sessions_recorded": summary["sessions_recorded"],
                "sessions_attended": summary["sessions_attended"],
                "percentage": summary["percentage"],
            }
        )


class ExamEligibilityView(APIView):
    """FR-ATT-02: is this registration clear to sit its exam? Restricted to
    the offices that decide eligibility, not everyone who may browse a
    register — a lecturer taking attendance has no reason to see this."""

    permission_classes = [HasModulePermission]
    required_permission = None

    @extend_schema(responses={200: ExamEligibilitySerializer})
    def get(self, request: Request, registration_id: int) -> Response:
        if not (
            request.user.has_role(*ELIGIBILITY_ROLES)
            or _is_own_registration(request, registration_id)
        ):
            return Response(
                error_envelope("permission_denied", "You may not view this record."), status=403
            )
        return Response(ExamEligibilitySerializer(services.exam_eligibility(registration_id)).data)


class GrantWaiverView(APIView):
    """FR-ATT-02: authorise a registration to sit despite a low attendance
    percentage."""

    permission_classes = [HasModulePermission]
    required_permission = "attendance.override_block"

    @extend_schema(request=GrantWaiverSerializer, responses={200: ExamEligibilitySerializer})
    def post(self, request: Request, registration_id: int) -> Response:
        serializer = GrantWaiverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.grant_waiver(
            registration_id, actor=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(ExamEligibilitySerializer(services.exam_eligibility(registration_id)).data)


def _is_own_registration(request: Request, registration_id: int) -> bool:
    from apps.enrollment.services import student_id_for_registration

    student_profile = getattr(request.user, "student_profile", None)
    if student_profile is None:
        return False
    return student_id_for_registration(registration_id) == student_profile.pk


def _may_view(request: Request, registration_id: int) -> bool:
    if request.user.has_role(*UNSCOPED_ROLES):
        return True
    return _is_own_registration(request, registration_id)
