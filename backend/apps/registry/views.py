from __future__ import annotations

import csv
import io

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.mixins import ScopedQuerysetMixin
from apps.core.exceptions import DomainError
from apps.core.mixins import CreateWithResponseSerializerMixin
from apps.core.permissions import HasModulePermission
from apps.registry import services
from apps.registry.models import Sponsor, StaffProfile, Student, StudentStatusHistory
from apps.registry.serializers import (
    BulkImportRequestSerializer,
    BulkImportResultSerializer,
    SponsorSerializer,
    StaffProfileSerializer,
    StatusChangeSerializer,
    StudentCreateSerializer,
    StudentListSerializer,
    StudentSerializer,
    StudentStatusHistorySerializer,
)


class StudentViewSet(ScopedQuerysetMixin, CreateWithResponseSerializerMixin, viewsets.ModelViewSet):
    """Student records.

    Holding `registry.view_student` answers "may this user read student records?".
    It does not answer "which ones?" — that is what the scoping below is for. A
    lecturer with the permission still sees only their own students.
    """

    queryset = Student.objects.select_related(
        "programme", "programme__department", "entry_academic_year", "sponsor"
    )
    response_serializer_class = StudentSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "registry.view_student",
        "POST": "registry.add_student",
        "PUT": "registry.change_student",
        "PATCH": "registry.change_student",
        "DELETE": "registry.delete_student",
    }

    filterset_fields = [
        "status",
        "programme",
        "current_level",
        "gender",
        "sponsorship_type",
        "has_disability",
        "state_of_origin",
        "entry_academic_year",
    ]
    search_fields = ["student_id", "first_name", "middle_name", "last_name", "national_id_number"]
    ordering_fields = ["last_name", "student_id", "current_level", "created_at"]
    ordering = ["last_name", "first_name"]

    # Row-level scoping
    unscoped_roles = {"registrar", "ict_admin", "management", "examinations", "finance", "hr"}
    scope_methods = {
        "student": "scope_to_self",
        "lecturer": "scope_to_taught",
        "hod": "scope_to_department",
        "library": "scope_to_all_minimal",
        "hostel": "scope_to_all_minimal",
    }

    def get_serializer_class(self):  # type: ignore[override]
        if self.action == "create":
            return StudentCreateSerializer
        if self.action == "list":
            return StudentListSerializer
        return StudentSerializer

    # ---- scoping rules ----

    def scope_to_self(self, queryset: QuerySet, user) -> QuerySet:
        return queryset.filter(user=user)

    def scope_to_taught(self, queryset: QuerySet, user) -> QuerySet:
        """Students on the lecturer's own courses.

        Course allocation arrives in Phase 3. Until then this narrows to the
        lecturer's department, which is stricter than showing everything and does
        not pretend to a precision the data cannot yet support.
        """
        profile = getattr(user, "staff_profile", None)
        if profile is None or profile.department_id is None:
            return queryset.none()
        return queryset.filter(programme__department_id=profile.department_id)

    def scope_to_department(self, queryset: QuerySet, user) -> QuerySet:
        profile = getattr(user, "staff_profile", None)
        if profile is None or profile.department_id is None:
            return queryset.none()
        return queryset.filter(programme__department_id=profile.department_id)

    def scope_to_all_minimal(self, queryset: QuerySet, user) -> QuerySet:
        """Library and hostel staff need to identify any student at a counter, but
        only active ones."""
        return queryset.filter(status="active")

    # ---- writes ----

    def perform_create(self, serializer) -> None:
        data = dict(serializer.validated_data)
        programme = data.pop("programme")
        entry_year = data.pop("entry_academic_year")

        student = services.create_student(
            programme_id=programme.pk,
            entry_academic_year_id=entry_year.pk,
            first_name=data.pop("first_name"),
            last_name=data.pop("last_name"),
            gender=data.pop("gender"),
            actor=self.request.user,
            **data,
        )
        serializer.instance = student

    def perform_update(self, serializer) -> None:
        instance = serializer.instance
        instance.audit_reason = self.request.data.get("audit_reason", "Updated via API")
        serializer.save()

    @extend_schema(
        summary="Change a student's status",
        request=StatusChangeSerializer,
        responses={200: StudentSerializer},
    )
    @action(detail=True, methods=["post"], url_path="change-status")
    def change_status(self, request: Request, pk: str | None = None) -> Response:
        """FR-REG-04. Separate from the update endpoint because a status change
        requires a reason and is subject to transition rules."""
        if not request.user.has_perm("registry.change_student_status"):
            return Response(
                {
                    "error": {
                        "code": "permission_denied",
                        "message": "You may not change student status.",
                        "details": {},
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        student = services.change_status(
            self.get_object(),
            serializer.validated_data["status"],
            reason=serializer.validated_data["reason"],
            actor=request.user,
            effective_date=serializer.validated_data.get("effective_date"),
            reference=serializer.validated_data.get("reference", ""),
        )
        return Response(StudentSerializer(student).data)

    @extend_schema(
        summary="Status history", responses={200: StudentStatusHistorySerializer(many=True)}
    )
    @action(detail=True, methods=["get"], url_path="status-history")
    def status_history(self, request: Request, pk: str | None = None) -> Response:
        history = StudentStatusHistory.objects.filter(student=self.get_object()).select_related(
            "changed_by"
        )
        return Response(StudentStatusHistorySerializer(history, many=True).data)

    @extend_schema(summary="Holds blocking registration", responses={200: dict})
    @action(detail=True, methods=["get"])
    def holds(self, request: Request, pk: str | None = None) -> Response:
        """FR-ENR-03. Answered through the hold-provider registry, so this works
        the same whether the finance module is installed or not."""
        student = self.get_object()
        holds = services.registration_holds(student.pk)
        return Response(
            {
                "student_id": student.student_id,
                "holds": holds,
                "clear": not any(h["blocking"] for h in holds),
            }
        )


class BulkImportStudentsView(APIView):
    """NFR-DATA-03: bulk-import legacy student records from an uploaded CSV.

    Same all-or-nothing contract as the `import_students` management command
    it wraps — a dry run (`commit=false`, the default) validates every row
    and reports what would happen without writing anything, so a registrar
    can fix a spreadsheet before it touches the database. Reachable from the
    browser rather than only from a terminal on the server.
    """

    permission_classes = [HasModulePermission]
    required_permission = "registry.add_student"

    @extend_schema(
        summary="Bulk-import students from a CSV file",
        request=BulkImportRequestSerializer,
        responses={200: BulkImportResultSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = BulkImportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        upload = serializer.validated_data["file"]
        try:
            decoded = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DomainError("The file is not valid UTF-8 text.", code="bad_encoding") from exc

        rows = list(csv.DictReader(io.StringIO(decoded)))
        if not rows:
            raise DomainError("The file has no data rows.", code="empty_file")

        result = services.import_students(
            rows,
            commit=serializer.validated_data["commit"],
            actor=request.user,
            reason=serializer.validated_data["reason"],
        )
        return Response(BulkImportResultSerializer(result).data)


class SponsorViewSet(viewsets.ModelViewSet):
    queryset = Sponsor.objects.all()
    serializer_class = SponsorSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "registry.view_sponsor",
        "POST": "registry.add_sponsor",
        "PUT": "registry.change_sponsor",
        "PATCH": "registry.change_sponsor",
        "DELETE": "registry.delete_sponsor",
    }
    filterset_fields = ["sponsor_type", "is_active"]
    search_fields = ["name", "contact_person"]


class StaffProfileViewSet(viewsets.ModelViewSet):
    queryset = StaffProfile.objects.select_related("user", "department")
    serializer_class = StaffProfileSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "registry.view_staffprofile",
        "POST": "registry.add_staffprofile",
        "PUT": "registry.change_staffprofile",
        "PATCH": "registry.change_staffprofile",
        "DELETE": "registry.delete_staffprofile",
    }
    filterset_fields = ["department", "staff_category", "rank", "appointment_type", "is_active"]
    search_fields = ["staff_number", "user__first_name", "user__last_name", "user__email"]
