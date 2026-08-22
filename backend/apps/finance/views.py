from __future__ import annotations

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.services import config as academics_config
from apps.accounts.mixins import ScopedQuerysetMixin
from apps.core.exceptions import error_envelope
from apps.core.mixins import CreateWithResponseSerializerMixin
from apps.core.permissions import HasModulePermission, IsAuthenticatedAndActive
from apps.finance import services
from apps.finance.models import FeeStructure, Invoice, Payment, Refund, Scholarship
from apps.finance.serializers import (
    DecideRefundSerializer,
    DefaulterRowSerializer,
    FeeStructureSerializer,
    GenerateInvoiceSerializer,
    GenerateInvoicesForSemesterSerializer,
    InitiateMobilePaymentSerializer,
    InvoiceSerializer,
    PaymentSerializer,
    RecordManualPaymentSerializer,
    RefundSerializer,
    RejectPaymentSerializer,
    RequestRefundSerializer,
    ScholarshipSerializer,
)

UNSCOPED_ROLES = {"registrar", "ict_admin", "management", "finance"}


class FeeStructureViewSet(viewsets.ModelViewSet):
    queryset = FeeStructure.objects.select_related("programme", "academic_year")
    serializer_class = FeeStructureSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "finance.view_feestructure",
        "POST": "finance.add_feestructure",
        "PUT": "finance.change_feestructure",
        "PATCH": "finance.change_feestructure",
    }
    filterset_fields = ["programme", "academic_year", "level", "residency", "is_active"]

    def perform_create(self, serializer) -> None:
        data = serializer.validated_data
        serializer.instance = services.create_fee_structure(
            programme_id=data["programme"].pk,
            academic_year_id=data["academic_year"].pk,
            level=data["level"],
            residency=data["residency"],
            amount=data["amount"],
            currency=data.get("currency"),
            actor=self.request.user,
        )

    def perform_update(self, serializer) -> None:
        data = serializer.validated_data
        serializer.instance = services.update_fee_structure(
            serializer.instance,
            amount=data.get("amount"),
            is_active=data.get("is_active"),
            actor=self.request.user,
        )


class InvoiceViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    """Invoices are never created through a raw POST — the amount comes from
    a fee structure lookup, never from what a client sends. `generate`/
    `generate-for-semester` are the only ways one comes into existence."""

    queryset = Invoice.objects.select_related("student", "semester", "fee_structure")
    serializer_class = InvoiceSerializer
    permission_classes = [HasModulePermission]
    required_permission = "finance.view_invoice"
    filterset_fields = ["student", "semester", "status"]
    ordering = ["-created_at"]

    unscoped_roles = UNSCOPED_ROLES
    scope_methods = {"student": "scope_to_self"}

    def scope_to_self(self, queryset: QuerySet, user) -> QuerySet:
        return queryset.filter(student__user=user)

    @extend_schema(
        summary="Issue an invoice for one student's semester",
        request=GenerateInvoiceSerializer,
        responses={201: InvoiceSerializer},
    )
    @action(detail=False, methods=["post"])
    def generate(self, request: Request) -> Response:
        if not request.user.has_perm("finance.add_invoice"):
            return Response(
                error_envelope("permission_denied", "You may not issue invoices."), status=403
            )
        serializer = GenerateInvoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        invoice = services.generate_invoice(
            student_id=data["student"],
            semester_id=data["semester"],
            due_date=data.get("due_date"),
            actor=request.user,
        )
        return Response(InvoiceSerializer(invoice).data, status=201)

    @extend_schema(
        summary="Issue invoices for every student registered this semester",
        request=GenerateInvoicesForSemesterSerializer,
        responses={200: dict},
    )
    @action(detail=False, methods=["post"], url_path="generate-for-semester")
    def generate_for_semester(self, request: Request) -> Response:
        if not request.user.has_perm("finance.add_invoice"):
            return Response(
                error_envelope("permission_denied", "You may not issue invoices."), status=403
            )
        serializer = GenerateInvoicesForSemesterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.generate_invoices_for_semester(
            semester_id=serializer.validated_data["semester"], actor=request.user
        )
        return Response(result)


class PaymentViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    """Browsing payments. Every write goes through a named action that
    enforces its own rule (confirmation only from pending, a reason to
    reject) — never a raw PATCH on the row."""

    queryset = Payment.objects.select_related("invoice", "invoice__student")
    serializer_class = PaymentSerializer
    permission_classes = [HasModulePermission]
    required_permission = "finance.view_payment"
    filterset_fields = ["invoice", "method", "status"]
    ordering = ["-created_at"]

    unscoped_roles = UNSCOPED_ROLES
    scope_methods = {"student": "scope_to_self"}

    def scope_to_self(self, queryset: QuerySet, user) -> QuerySet:
        return queryset.filter(invoice__student__user=user)

    @extend_schema(
        summary="Record a cash, cheque or bank-slip payment",
        request=RecordManualPaymentSerializer,
        responses={201: PaymentSerializer},
    )
    @action(detail=False, methods=["post"])
    def record(self, request: Request) -> Response:
        if not request.user.has_perm("finance.add_payment"):
            return Response(
                error_envelope("permission_denied", "You may not record payments."), status=403
            )
        serializer = RecordManualPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payment = services.record_manual_payment(
            invoice_id=data["invoice"],
            method=data["method"],
            amount=data["amount"],
            reference=data["reference"],
            actor=request.user,
            notes=data.get("notes", ""),
        )
        return Response(PaymentSerializer(payment).data, status=201)

    @extend_schema(
        summary="Confirm a pending cheque/bank-slip payment", responses={200: PaymentSerializer}
    )
    @action(detail=True, methods=["post"])
    def confirm(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("finance.change_payment"):
            return Response(
                error_envelope("permission_denied", "You may not confirm payments."), status=403
            )
        payment = services.confirm_manual_payment(self.get_object(), actor=request.user)
        return Response(PaymentSerializer(payment).data)

    @extend_schema(
        summary="Reject a pending cheque/bank-slip payment",
        request=RejectPaymentSerializer,
        responses={200: PaymentSerializer},
    )
    @action(detail=True, methods=["post"])
    def reject(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("finance.change_payment"):
            return Response(
                error_envelope("permission_denied", "You may not reject payments."), status=403
            )
        serializer = RejectPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = services.reject_manual_payment(
            self.get_object(), actor=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(PaymentSerializer(payment).data)

    @extend_schema(
        summary="Initiate a mobile-money payment",
        request=InitiateMobilePaymentSerializer,
        responses={201: PaymentSerializer},
    )
    @action(detail=False, methods=["post"], url_path="initiate-mobile")
    def initiate_mobile(self, request: Request) -> Response:
        serializer = InitiateMobilePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payment = services.initiate_mobile_payment(
            invoice_id=data["invoice"],
            payer_ref=data["payer_ref"],
            amount=data.get("amount"),
            actor=request.user,
        )
        return Response(PaymentSerializer(payment).data, status=201)

    @extend_schema(
        summary="Check a pending mobile-money payment against the provider",
        responses={200: PaymentSerializer},
    )
    @action(detail=True, methods=["post"])
    def poll(self, request: Request, pk: str | None = None) -> Response:
        payment = services.poll_mobile_payment(self.get_object())
        return Response(PaymentSerializer(payment).data)


class PaymentWebhookView(APIView):
    """The mobile-money provider's own callback — never a user session, so
    it is authorised entirely by `verify_callback`'s signature check, not by
    `HasModulePermission`."""

    permission_classes = [AllowAny]
    required_permission = None

    @extend_schema(summary="Mobile money provider webhook", responses={200: dict})
    def post(self, request: Request) -> Response:
        payment = services.handle_payment_webhook(request)
        return Response({"received": True, "payment_id": payment.pk if payment else None})


class ScholarshipViewSet(viewsets.ModelViewSet):
    queryset = Scholarship.objects.select_related("student", "sponsor", "academic_year")
    serializer_class = ScholarshipSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "finance.view_scholarship",
        "POST": "finance.add_scholarship",
        "PUT": "finance.change_scholarship",
        "PATCH": "finance.change_scholarship",
    }
    filterset_fields = ["student", "academic_year", "sponsor", "is_active"]

    def perform_create(self, serializer) -> None:
        data = serializer.validated_data
        serializer.instance = services.create_scholarship(
            student_id=data["student"].pk,
            academic_year_id=data["academic_year"].pk,
            coverage_type=data["coverage_type"],
            sponsor_id=data["sponsor"].pk if data.get("sponsor") else None,
            percentage=data.get("percentage"),
            fixed_amount=data.get("fixed_amount"),
            currency=data.get("currency"),
            notes=data.get("notes", ""),
            actor=self.request.user,
        )

    def perform_update(self, serializer) -> None:
        data = serializer.validated_data
        serializer.instance = services.update_scholarship(
            serializer.instance,
            percentage=data.get("percentage"),
            fixed_amount=data.get("fixed_amount"),
            is_active=data.get("is_active"),
            actor=self.request.user,
        )


class RefundViewSet(ScopedQuerysetMixin, CreateWithResponseSerializerMixin, viewsets.ModelViewSet):
    """A student requests their own refund; only finance decides one, via
    `decide` — never a raw PATCH on `status`."""

    http_method_names = ["get", "post", "head", "options"]
    queryset = Refund.objects.select_related("payment", "payment__invoice")
    serializer_class = RefundSerializer
    response_serializer_class = RefundSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "finance.view_refund",
        "POST": "finance.add_refund",
    }
    filterset_fields = ["payment", "status"]
    ordering = ["-created_at"]

    unscoped_roles = UNSCOPED_ROLES
    scope_methods = {"student": "scope_to_self"}

    def scope_to_self(self, queryset: QuerySet, user) -> QuerySet:
        return queryset.filter(payment__invoice__student__user=user)

    def get_serializer_class(self):  # type: ignore[override]
        if self.action == "create":
            return RequestRefundSerializer
        return RefundSerializer

    def perform_create(self, serializer) -> None:
        data = serializer.validated_data
        serializer.instance = services.request_refund(
            payment_id=data["payment"],
            amount=data["amount"],
            reason=data["reason"],
            actor=self.request.user,
        )

    @extend_schema(
        summary="Approve or reject a refund request",
        request=DecideRefundSerializer,
        responses={200: RefundSerializer},
    )
    @action(detail=True, methods=["post"])
    def decide(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("finance.approve_refund"):
            return Response(
                error_envelope("permission_denied", "You may not decide refund requests."),
                status=403,
            )
        serializer = DecideRefundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        refund = services.decide_refund(
            self.get_object(), approve=data["approve"], actor=request.user, notes=data["notes"]
        )
        return Response(RefundSerializer(refund).data)

    @extend_schema(
        summary="Record that an approved refund has been paid out",
        responses={200: RefundSerializer},
    )
    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("finance.approve_refund"):
            return Response(
                error_envelope("permission_denied", "You may not settle refunds."), status=403
            )
        refund = services.mark_refund_paid(self.get_object(), actor=request.user)
        return Response(RefundSerializer(refund).data)

    def get_permissions(self):  # type: ignore[override]
        # `required_permissions["POST"]` governs requesting a refund
        # (`finance.add_refund`, a student's own permission) — deciding one
        # is deliberately a different permission (`finance.approve_refund`,
        # FR-FIN-08's separation between whoever asks and whoever authorises),
        # so `decide`/`mark_paid` check their own rather than inheriting the
        # create gate just because both are POSTs.
        if self.action in {"decide", "mark_paid"}:
            return [IsAuthenticatedAndActive()]
        return super().get_permissions()


class DefaulterReportView(APIView):
    """FR-FIN-07."""

    permission_classes = [HasModulePermission]
    required_permission = "finance.view_defaulterreport"

    @extend_schema(
        summary="Students with an outstanding balance",
        responses={200: DefaulterRowSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        semester_id = request.query_params.get("semester")
        rows = services.defaulter_report(semester_id=int(semester_id) if semester_id else None)
        return Response(DefaulterRowSerializer(rows, many=True).data)


class FeeBalanceView(APIView):
    """A single student's outstanding balance — the number a registration
    form or the student portal shows live."""

    permission_classes = [HasModulePermission]
    required_permission = None

    def get(self, request: Request, student_id: int) -> Response:
        is_self = (
            hasattr(request.user, "student_profile")
            and request.user.student_profile.pk == student_id
        )
        if not is_self and not request.user.has_role(*UNSCOPED_ROLES):
            return Response(
                error_envelope("permission_denied", "You may not view this balance."), status=403
            )
        return Response(
            {
                "student_id": student_id,
                "balance": str(services.fee_balance_for_student(student_id)),
                "currency": academics_config.base_currency(),
            }
        )
