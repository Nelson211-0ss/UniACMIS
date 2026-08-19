from __future__ import annotations

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.mixins import ScopedQuerysetMixin
from apps.core.exceptions import error_envelope
from apps.core.mixins import CreateWithResponseSerializerMixin
from apps.core.permissions import HasModulePermission, IsAuthenticatedAndActive
from apps.examinations import services
from apps.examinations.models import Assessment, GradeAppeal, Mark, ResultApproval
from apps.examinations.serializers import (
    AssessmentSerializer,
    CourseResultSerializer,
    DecideAppealSerializer,
    DecisionNotesSerializer,
    GradeAppealSerializer,
    IrregularitySerializer,
    MarkSerializer,
    MissingMarkSerializer,
    ModerateMarkSerializer,
    RecordMarkSerializer,
    RejectApprovalSerializer,
    ResultApprovalSerializer,
    StudentResultSerializer,
    SubmitAppealSerializer,
    SubmitApprovalSerializer,
)

UNSCOPED_ROLES = {"registrar", "ict_admin", "management", "examinations"}


class AssessmentViewSet(CreateWithResponseSerializerMixin, viewsets.ModelViewSet):
    """A course's CA/exam scheme (FR-EXM-01). Owned by the examinations
    office, not individual lecturers, so a scheme cannot change mid-semester
    without the office that publishes results knowing about it."""

    queryset = Assessment.objects.select_related("course")
    serializer_class = AssessmentSerializer
    response_serializer_class = AssessmentSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "examinations.view_assessment",
        "POST": "examinations.add_assessment",
        "PUT": "examinations.change_assessment",
        "PATCH": "examinations.change_assessment",
    }
    filterset_fields = ["course"]
    ordering = ["course", "sequence"]

    def perform_create(self, serializer) -> None:
        data = serializer.validated_data
        serializer.instance = services.create_assessment(
            course_id=data["course"].pk,
            name=data["name"],
            weight_percent=data["weight_percent"],
            max_score=data.get("max_score", 100),
            sequence=data.get("sequence", 1),
            grade_entry_deadline=data.get("grade_entry_deadline"),
            actor=self.request.user,
        )

    def perform_update(self, serializer) -> None:
        data = serializer.validated_data
        serializer.instance = services.update_assessment(
            serializer.instance,
            name=data.get("name"),
            weight_percent=data.get("weight_percent"),
            max_score=data.get("max_score"),
            sequence=data.get("sequence"),
            grade_entry_deadline=data.get("grade_entry_deadline", "__unset__"),
            actor=self.request.user,
        )


class MarkViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    """Browsing marks. Entry and correction go through `record`, moderation
    and irregularity flags through their own actions — never a plain PATCH,
    so every write is the one this module's specific rules govern (FR-EXM-01,
    FR-EXM-03, FR-EXM-08)."""

    queryset = Mark.objects.select_related("registration__student", "assessment__course")
    serializer_class = MarkSerializer
    permission_classes = [HasModulePermission]
    required_permission = "examinations.view_mark"
    filterset_fields = ["registration", "assessment", "is_irregular"]
    ordering = ["-created_at"]

    unscoped_roles = UNSCOPED_ROLES
    scope_methods = {
        "student": "scope_to_self",
        "lecturer": "scope_to_department",
        "hod": "scope_to_department",
        "senate": "scope_to_all",
    }

    def scope_to_self(self, queryset: QuerySet, user) -> QuerySet:
        return queryset.filter(registration__student__user=user)

    def scope_to_department(self, queryset: QuerySet, user) -> QuerySet:
        profile = getattr(user, "staff_profile", None)
        if profile is None or profile.department_id is None:
            return queryset.none()
        return queryset.filter(registration__course__department_id=profile.department_id)

    def scope_to_all(self, queryset: QuerySet, user) -> QuerySet:
        return queryset

    @extend_schema(
        summary="Record or correct a mark",
        request=RecordMarkSerializer,
        responses={200: MarkSerializer},
    )
    @action(detail=False, methods=["post"])
    def record(self, request: Request) -> Response:
        if not request.user.has_perm("examinations.add_mark"):
            return Response(
                error_envelope("permission_denied", "You may not record marks."), status=403
            )
        serializer = RecordMarkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        mark = services.record_mark(
            registration_id=data["registration"],
            assessment_id=data["assessment"],
            score=data["score"],
            actor=request.user,
        )
        return Response(MarkSerializer(mark).data)

    @extend_schema(
        summary="Moderate (second-mark) a mark",
        request=ModerateMarkSerializer,
        responses={200: MarkSerializer},
    )
    @action(detail=True, methods=["post"])
    def moderate(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("examinations.moderate_result"):
            return Response(
                error_envelope("permission_denied", "You may not moderate marks."), status=403
            )
        serializer = ModerateMarkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mark = services.moderate_mark(
            self.get_object(),
            moderated_score=serializer.validated_data["moderated_score"],
            notes=serializer.validated_data["notes"],
            actor=request.user,
        )
        return Response(MarkSerializer(mark).data)

    @extend_schema(
        summary="Flag an exam irregularity",
        request=IrregularitySerializer,
        responses={200: MarkSerializer},
    )
    @action(detail=True, methods=["post"], url_path="flag-irregularity")
    def flag_irregularity(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("examinations.flag_irregularity"):
            return Response(
                error_envelope("permission_denied", "You may not flag an irregularity."), status=403
            )
        serializer = IrregularitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mark = services.flag_irregularity(
            self.get_object(), notes=serializer.validated_data["notes"], actor=request.user
        )
        return Response(MarkSerializer(mark).data)

    @extend_schema(summary="Clear an exam irregularity flag", responses={200: MarkSerializer})
    @action(detail=True, methods=["post"], url_path="clear-irregularity")
    def clear_irregularity(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("examinations.flag_irregularity"):
            return Response(
                error_envelope("permission_denied", "You may not clear an irregularity."),
                status=403,
            )
        mark = services.clear_irregularity(self.get_object(), actor=request.user)
        return Response(MarkSerializer(mark).data)


class MissingMarksView(APIView):
    """FR-EXM-08: who is registered but has no mark yet for a component."""

    permission_classes = [HasModulePermission]
    required_permission = "examinations.view_mark"

    @extend_schema(responses={200: MissingMarkSerializer(many=True)})
    def get(self, request: Request) -> Response:
        course_id = request.query_params.get("course")
        semester_id = request.query_params.get("semester")
        if not course_id or not semester_id:
            return Response(
                error_envelope("bad_request", "Both `course` and `semester` are required."),
                status=400,
            )
        report = services.missing_marks_report(int(course_id), int(semester_id))
        return Response(MissingMarkSerializer(report, many=True).data)


class CourseResultView(APIView):
    """A single registration's computed result (FR-EXM-04)."""

    permission_classes = [HasModulePermission]
    required_permission = "examinations.view_mark"

    @extend_schema(responses={200: CourseResultSerializer})
    def get(self, request: Request, registration_id: int) -> Response:
        return Response(CourseResultSerializer(services.course_result(registration_id)).data)


class StudentResultView(APIView):
    """What a student is shown for a semester (FR-EXM-04…06): their own, or
    an unscoped office's view of anyone's."""

    permission_classes = [HasModulePermission]
    required_permission = None

    @extend_schema(responses={200: StudentResultSerializer})
    def get(self, request: Request, student_id: int, semester_id: int) -> Response:
        is_self = (
            hasattr(request.user, "student_profile")
            and request.user.student_profile.pk == student_id
        )
        if not is_self and not request.user.has_role(*UNSCOPED_ROLES):
            return Response(
                error_envelope("permission_denied", "You may not view this student's result."),
                status=403,
            )
        return Response(
            StudentResultSerializer(services.student_result(student_id, semester_id)).data
        )


class GradeAppealViewSet(
    ScopedQuerysetMixin, CreateWithResponseSerializerMixin, viewsets.ModelViewSet
):
    """FR-EXM-07. A student submits their own; the HOD or examinations office
    decides — never the same person who could also change the mark it
    concerns without a visible decision on record."""

    http_method_names = ["get", "post", "head", "options"]
    queryset = GradeAppeal.objects.select_related("registration__student", "assessment")
    serializer_class = GradeAppealSerializer
    response_serializer_class = GradeAppealSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "examinations.view_gradeappeal",
        "POST": "examinations.add_gradeappeal",
    }
    filterset_fields = ["status", "registration"]
    ordering = ["-created_at"]

    unscoped_roles = {"registrar", "ict_admin", "management", "examinations", "hod"}
    scope_methods = {"student": "scope_to_self"}

    def scope_to_self(self, queryset: QuerySet, user) -> QuerySet:
        return queryset.filter(registration__student__user=user)

    def get_serializer_class(self):  # type: ignore[override]
        if self.action == "create":
            return SubmitAppealSerializer
        return GradeAppealSerializer

    def get_permissions(self):  # type: ignore[override]
        # `required_permissions["POST"]` governs submitting a new appeal
        # (`examinations.add_gradeappeal`, a student's own permission) — the
        # decider is a different office entirely and does not hold that
        # permission, so `decide` checks its own (`decide_gradeappeal`)
        # instead of inheriting the create gate just because both are POSTs.
        if self.action == "decide":
            return [IsAuthenticatedAndActive()]
        return super().get_permissions()

    def perform_create(self, serializer) -> None:
        data = serializer.validated_data
        serializer.instance = services.submit_appeal(
            registration_id=data["registration"],
            assessment_id=data.get("assessment"),
            reason=data["reason"],
            actor=self.request.user,
        )

    @extend_schema(
        summary="Decide a grade appeal",
        request=DecideAppealSerializer,
        responses={200: GradeAppealSerializer},
    )
    @action(detail=True, methods=["post"])
    def decide(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("examinations.decide_gradeappeal"):
            return Response(
                error_envelope("permission_denied", "You may not decide grade appeals."), status=403
            )
        serializer = DecideAppealSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        appeal = services.decide_appeal(
            self.get_object(),
            decision=serializer.validated_data["decision"],
            notes=serializer.validated_data["notes"],
            actor=request.user,
        )
        return Response(GradeAppealSerializer(appeal).data)


class ResultApprovalViewSet(CreateWithResponseSerializerMixin, viewsets.ModelViewSet):
    """FR-EXM-05. The examinations office submits and (once approved)
    publishes; only Senate approves — never the same permission for both."""

    http_method_names = ["get", "post", "head", "options"]
    queryset = ResultApproval.objects.select_related("semester", "programme")
    serializer_class = ResultApprovalSerializer
    response_serializer_class = ResultApprovalSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "examinations.view_mark",
        "POST": "examinations.publish_result",
    }
    filterset_fields = ["semester", "programme", "status"]
    ordering = ["-created_at"]

    def get_serializer_class(self):  # type: ignore[override]
        if self.action == "create":
            return SubmitApprovalSerializer
        return ResultApprovalSerializer

    def get_permissions(self):  # type: ignore[override]
        # `required_permissions["POST"]` governs submitting results for
        # approval (`examinations.publish_result`, the office's own
        # permission) — Senate approves and rejects under a *different*
        # permission it holds instead (`approve_result`), by design
        # (FR-EXM-05: the office that prepares results must not also
        # approve them), so those two actions check their own permission
        # rather than inheriting the create gate just because both are POSTs.
        if self.action in {"approve", "reject"}:
            return [IsAuthenticatedAndActive()]
        return super().get_permissions()

    def perform_create(self, serializer) -> None:
        data = serializer.validated_data
        serializer.instance = services.submit_for_approval(
            semester_id=data["semester"],
            programme_id=data.get("programme"),
            actor=self.request.user,
        )

    @extend_schema(
        summary="Approve a semester's results (Senate)",
        request=DecisionNotesSerializer,
        responses={200: ResultApprovalSerializer},
    )
    @action(detail=True, methods=["post"])
    def approve(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("examinations.approve_result"):
            return Response(
                error_envelope("permission_denied", "You may not approve results."), status=403
            )
        serializer = DecisionNotesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        approval = services.approve_results(
            self.get_object(), actor=request.user, notes=serializer.validated_data.get("notes", "")
        )
        return Response(ResultApprovalSerializer(approval).data)

    @extend_schema(
        summary="Reject a semester's results (Senate)",
        request=RejectApprovalSerializer,
        responses={200: ResultApprovalSerializer},
    )
    @action(detail=True, methods=["post"])
    def reject(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("examinations.approve_result"):
            return Response(
                error_envelope("permission_denied", "You may not reject results."), status=403
            )
        serializer = RejectApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        approval = services.reject_results(
            self.get_object(), actor=request.user, notes=serializer.validated_data["notes"]
        )
        return Response(ResultApprovalSerializer(approval).data)

    @extend_schema(
        summary="Publish approved results to students", responses={200: ResultApprovalSerializer}
    )
    @action(detail=True, methods=["post"])
    def publish(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("examinations.publish_result"):
            return Response(
                error_envelope("permission_denied", "You may not publish results."), status=403
            )
        approval = services.publish_results(self.get_object(), actor=request.user)
        return Response(ResultApprovalSerializer(approval).data)
