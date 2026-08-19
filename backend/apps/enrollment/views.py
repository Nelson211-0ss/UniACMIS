from __future__ import annotations

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.mixins import ScopedQuerysetMixin
from apps.core.exceptions import error_envelope
from apps.core.mixins import CreateWithResponseSerializerMixin
from apps.core.permissions import HasModulePermission
from apps.enrollment import services
from apps.enrollment.models import CourseRegistration
from apps.enrollment.serializers import (
    ClassListEntrySerializer,
    CompletionSerializer,
    CourseRegistrationSerializer,
    CreditSummarySerializer,
    DropCourseSerializer,
    RegisterCourseSerializer,
)


class CourseRegistrationViewSet(
    ScopedQuerysetMixin, CreateWithResponseSerializerMixin, viewsets.ModelViewSet
):
    """Course registrations. A student registers and drops their own; the
    registrar (and, for a hold override, only the registrar) may act on
    anyone's — the same "own record vs. everyone" shape as every other
    scoped viewset in this system.

    No generic update or delete: every mutation beyond creation goes through a
    named action (`drop`, `complete`) that enforces its own rule (a reason, the
    add/drop window, who may record a completion). A raw PATCH could otherwise
    set `status` directly and skip all of it, so PUT/PATCH/DELETE are excluded
    from `http_method_names` — a 405, not merely a 403 an omitted permission
    would produce, because the method is not merely restricted here, it does
    not exist.
    """

    http_method_names = ["get", "post", "head", "options"]
    queryset = CourseRegistration.objects.select_related("student", "course", "semester")
    serializer_class = RegisterCourseSerializer
    response_serializer_class = CourseRegistrationSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "enrollment.view_courseregistration",
        "POST": "enrollment.add_courseregistration",
    }
    filterset_fields = ["status", "course", "semester", "is_repeat"]
    ordering = ["-created_at"]

    unscoped_roles = {"registrar", "ict_admin", "management"}
    scope_methods = {
        "student": "scope_to_self",
        "lecturer": "scope_to_department",
        "hod": "scope_to_department",
    }

    def get_serializer_class(self):  # type: ignore[override]
        if self.action in {"list", "retrieve"}:
            return CourseRegistrationSerializer
        return RegisterCourseSerializer

    def scope_to_self(self, queryset: QuerySet, user) -> QuerySet:
        return queryset.filter(student__user=user)

    def scope_to_department(self, queryset: QuerySet, user) -> QuerySet:
        profile = getattr(user, "staff_profile", None)
        if profile is None or profile.department_id is None:
            return queryset.none()
        return queryset.filter(course__department_id=profile.department_id)

    def perform_create(self, serializer) -> None:
        data = serializer.validated_data
        semester = data.get("semester")
        registration = services.register_course(
            student_id=data["student"].pk,
            course_id=data["course"].pk,
            semester_id=semester.pk if semester else None,
            actor=self.request.user,
            override_reason=data.get("override_reason", ""),
        )
        serializer.instance = registration

    @extend_schema(
        summary="Drop a course",
        request=DropCourseSerializer,
        responses={200: CourseRegistrationSerializer},
    )
    @action(detail=True, methods=["post"])
    def drop(self, request: Request, pk: str | None = None) -> Response:
        serializer = DropCourseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        registration = services.drop_course(
            self.get_object(), reason=serializer.validated_data["reason"], actor=request.user
        )
        return Response(CourseRegistrationSerializer(registration).data)

    @extend_schema(
        summary="Record as completed (transfer credit / legacy record)",
        request=CompletionSerializer,
        responses={200: CourseRegistrationSerializer},
    )
    @action(detail=True, methods=["post"], url_path="complete")
    def complete_registration(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("enrollment.record_completion"):
            return Response(
                error_envelope("permission_denied", "You may not record a completion."),
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = CompletionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        registration = services.record_prior_completion(
            self.get_object(), actor=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(CourseRegistrationSerializer(registration).data)


class ClassListView(APIView):
    """FR-ENR-04: the register for one course in one semester."""

    permission_classes = [HasModulePermission]
    required_permission = "enrollment.view_courseregistration"

    @extend_schema(
        summary="Class list for a course", responses={200: ClassListEntrySerializer(many=True)}
    )
    def get(self, request: Request) -> Response:
        course_id = request.query_params.get("course")
        semester_id = request.query_params.get("semester")
        if not course_id or not semester_id:
            return Response(
                error_envelope("bad_request", "Both `course` and `semester` are required."),
                status=status.HTTP_400_BAD_REQUEST,
            )
        entries = services.class_list(int(course_id), int(semester_id))
        return Response(ClassListEntrySerializer(entries, many=True).data)


class CreditSummaryView(APIView):
    """How many credits a student is carrying against their programme's
    min/max for a semester — the number a registration form shows live."""

    permission_classes = [HasModulePermission]
    required_permission = None

    # Deliberately role-based, not `has_perm("enrollment.view_courseregistration")`:
    # a student holds that same permission too, scoped to their own rows by the
    # registrations viewset — treating it as sufficient here would let any
    # student read any other student's credit load, since this view has no
    # queryset to scope in the first place.
    unscoped_roles = CourseRegistrationViewSet.unscoped_roles

    @extend_schema(
        summary="A student's registered credit load", responses={200: CreditSummarySerializer}
    )
    def get(self, request: Request, student_id: int) -> Response:
        from apps.academics.services import calendar

        is_self = (
            hasattr(request.user, "student_profile")
            and request.user.student_profile.pk == student_id
        )
        is_unscoped = request.user.has_role(*self.unscoped_roles)
        if not is_self and not is_unscoped:
            return Response(
                error_envelope("permission_denied", "You may not view this student's credit load."),
                status=status.HTTP_403_FORBIDDEN,
            )

        semester_id = request.query_params.get("semester")
        semester = (
            calendar.get_semester(int(semester_id))
            if semester_id
            else calendar.require_current_semester()
        )
        summary = services.credit_summary(student_id, semester.pk)
        return Response(CreditSummarySerializer(summary).data)
