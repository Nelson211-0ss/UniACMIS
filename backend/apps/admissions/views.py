from __future__ import annotations

from decimal import Decimal

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.mixins import ScopedQuerysetMixin
from apps.admissions import services
from apps.admissions.models import Application
from apps.admissions.serializers import (
    ApplicationCreateSerializer,
    ApplicationDocumentSerializer,
    ApplicationListSerializer,
    ApplicationSerializer,
    DecisionSerializer,
    MeritListEntrySerializer,
    ReviewSubmitSerializer,
    WithdrawSerializer,
)
from apps.core.exceptions import error_envelope
from apps.core.mixins import CreateWithResponseSerializerMixin
from apps.core.permissions import HasModulePermission


class ApplicationViewSet(
    ScopedQuerysetMixin, CreateWithResponseSerializerMixin, viewsets.ModelViewSet
):
    """Applications, scoped to "my own" for applicants and "everyone" for the
    registrar — the same shape as StudentViewSet's scoping in Phase 1."""

    queryset = Application.objects.select_related(
        "programme", "intended_academic_year"
    ).prefetch_related("documents", "reviews", "fee_payments")
    response_serializer_class = ApplicationSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "admissions.view_application",
        "POST": "admissions.add_application",
        "PUT": "admissions.change_application",
        "PATCH": "admissions.change_application",
    }
    filterset_fields = ["status", "programme", "intended_academic_year", "source"]
    search_fields = ["reference_number", "first_name", "last_name", "national_id_number"]
    ordering = ["-created_at"]

    unscoped_roles = {"registrar", "management", "ict_admin"}
    scope_methods = {"applicant": "scope_to_self", "student": "scope_to_self"}

    def scope_to_self(self, queryset: QuerySet, user) -> QuerySet:
        return queryset.filter(user=user)

    def get_serializer_class(self):  # type: ignore[override]
        if self.action == "create":
            return ApplicationCreateSerializer
        if self.action == "list":
            return ApplicationListSerializer
        return ApplicationSerializer

    def perform_create(self, serializer) -> None:
        data = dict(serializer.validated_data)
        programme = data.pop("programme")
        year = data.pop("intended_academic_year")
        is_applicant = (
            self.request.user.has_role("applicant")
            if hasattr(self.request.user, "has_role")
            else False
        )

        application = services.create_application(
            programme_id=programme.pk,
            intended_academic_year_id=year.pk,
            first_name=data.pop("first_name"),
            last_name=data.pop("last_name"),
            gender=data.pop("gender"),
            source="self_service" if is_applicant else "staff_entry",
            applicant_user=self.request.user if is_applicant else None,
            entered_by=None if is_applicant else self.request.user,
            **data,
        )
        serializer.instance = application

    def perform_update(self, serializer) -> None:
        from apps.admissions.models import ApplicationStatus

        instance: Application = serializer.instance
        if instance.status != ApplicationStatus.DRAFT:
            from apps.core.exceptions import DomainError

            raise DomainError(
                "Only a draft application can be edited directly. Use the specific "
                "actions (submit, withdraw, review, decide) for anything else.",
                code="not_editable",
            )
        instance.audit_reason = "Edited before submission"
        serializer.save()

    @extend_schema(summary="Submit an application", responses={200: ApplicationSerializer})
    @action(detail=True, methods=["post"])
    def submit(self, request: Request, pk: str | None = None) -> Response:
        application = services.submit_application(self.get_object())
        return Response(ApplicationSerializer(application).data)

    @extend_schema(
        summary="Withdraw an application",
        request=WithdrawSerializer,
        responses={200: ApplicationSerializer},
    )
    @action(detail=True, methods=["post"])
    def withdraw(self, request: Request, pk: str | None = None) -> Response:
        serializer = WithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = services.withdraw_application(
            self.get_object(), reason=serializer.validated_data["reason"]
        )
        return Response(ApplicationSerializer(application).data)

    @extend_schema(
        summary="Score an application (admissions committee)",
        request=ReviewSubmitSerializer,
        responses={200: ApplicationSerializer},
    )
    @action(detail=True, methods=["post"], url_path="review")
    def add_review(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("admissions.add_applicationreview"):
            return Response(
                error_envelope("permission_denied", "You may not review applications."),
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = ReviewSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.record_review(
            self.get_object(),
            reviewer=request.user,
            score=serializer.validated_data["score"],
            criteria=serializer.validated_data.get("criteria"),
            comments=serializer.validated_data.get("comments", ""),
        )
        return Response(ApplicationSerializer(self.get_object()).data)

    @extend_schema(
        summary="Offer or reject",
        request=DecisionSerializer,
        responses={200: ApplicationSerializer},
    )
    @action(detail=True, methods=["post"])
    def decide(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("admissions.decide_application"):
            return Response(
                error_envelope("permission_denied", "You may not decide applications."),
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = DecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = services.decide_application(
            self.get_object(),
            serializer.validated_data["decision"],
            decided_by=request.user,
            reason=serializer.validated_data["reason"],
        )
        return Response(ApplicationSerializer(application).data)

    @extend_schema(summary="Accept an offer (applicant)", responses={200: ApplicationSerializer})
    @action(detail=True, methods=["post"], url_path="accept-offer")
    def accept_offer(self, request: Request, pk: str | None = None) -> Response:
        application = services.accept_offer(self.get_object(), actor=request.user)
        return Response(ApplicationSerializer(application).data)

    @extend_schema(summary="Decline an offer (applicant)", responses={200: ApplicationSerializer})
    @action(detail=True, methods=["post"], url_path="decline-offer")
    def decline_offer_action(self, request: Request, pk: str | None = None) -> Response:
        application = services.decline_offer(self.get_object())
        return Response(ApplicationSerializer(application).data)

    @extend_schema(summary="Convert an accepted application into a student", responses={200: dict})
    @action(detail=True, methods=["post"])
    def convert(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("admissions.decide_application"):
            return Response(
                error_envelope("permission_denied", "You may not convert applications."),
                status=status.HTTP_403_FORBIDDEN,
            )
        student = services.convert_to_student(self.get_object(), actor=request.user)
        return Response({"student_id": student.student_id, "id": student.pk})

    @extend_schema(summary="Upload a document", responses={201: ApplicationDocumentSerializer})
    @action(detail=True, methods=["post"], url_path="documents")
    def upload_document(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("admissions.add_applicationdocument"):
            return Response(
                error_envelope("permission_denied", "You may not upload documents here."),
                status=status.HTTP_403_FORBIDDEN,
            )
        document = services.attach_document(
            application=self.get_object(),
            document_type=request.data.get("document_type", "other"),
            title=request.data.get("title", ""),
            file=request.data["file"],
            uploaded_by=request.user,
        )
        return Response(
            ApplicationDocumentSerializer(document).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(summary="Initiate the application fee payment", responses={201: dict})
    @action(detail=True, methods=["post"], url_path="initiate-payment")
    def initiate_payment(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("admissions.add_applicationfeepayment"):
            return Response(
                error_envelope("permission_denied", "You may not record a payment here."),
                status=status.HTTP_403_FORBIDDEN,
            )
        payment = services.initiate_fee_payment(
            self.get_object(),
            Decimal(str(request.data.get("amount"))),
            request.data.get("currency", "SSP"),
        )
        return Response(
            {"reference": payment.reference, "status": payment.status},
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(summary="Confirm a fee payment against the provider", responses={200: dict})
    @action(detail=True, methods=["post"], url_path="confirm-payment")
    def confirm_payment(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("admissions.change_applicationfeepayment"):
            return Response(
                error_envelope("permission_denied", "You may not confirm payments."),
                status=status.HTTP_403_FORBIDDEN,
            )
        reference = request.data.get("reference")
        payment = self.get_object().fee_payments.get(reference=reference)
        payment = services.confirm_fee_payment(payment)
        return Response({"reference": payment.reference, "status": payment.status})


class MeritListView(APIView):
    """FR-ADM-06. Sensitive — reveals rankings and scores across every
    applicant to one programme/intake, so it is gated on the same permission
    as making a decision, not merely viewing one application."""

    permission_classes = [HasModulePermission]
    required_permission = "admissions.decide_application"

    @extend_schema(
        summary="Generate the merit list", responses={200: MeritListEntrySerializer(many=True)}
    )
    def get(self, request: Request) -> Response:
        programme_id = request.query_params.get("programme")
        year_id = request.query_params.get("academic_year")
        if not programme_id or not year_id:
            return Response(
                error_envelope("bad_request", "Both `programme` and `academic_year` are required."),
                status=status.HTTP_400_BAD_REQUEST,
            )
        entries = services.build_merit_list(int(programme_id), int(year_id))
        return Response(MeritListEntrySerializer(entries, many=True).data)
