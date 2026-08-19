from __future__ import annotations

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import error_envelope
from apps.core.permissions import HasModulePermission, IsAuthenticatedAndActive
from apps.hr import services
from apps.hr.models import Appraisal, Contract, LeaveRequest
from apps.hr.serializers import (
    AppraisalSerializer,
    ContractSerializer,
    DecideLeaveRequestSerializer,
    EndContractSerializer,
    LeaveRequestSerializer,
    PayrollRowSerializer,
    SubmitLeaveRequestSerializer,
)

UNSCOPED_ROLES = {"hr", "ict_admin", "management"}


class ContractViewSet(viewsets.ModelViewSet):
    queryset = Contract.objects.select_related("staff", "staff__user")
    serializer_class = ContractSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "hr.view_contract",
        "POST": "hr.add_contract",
        "PUT": "hr.change_contract",
        "PATCH": "hr.change_contract",
    }
    filterset_fields = ["staff", "contract_type", "is_active"]

    def perform_create(self, serializer) -> None:
        data = serializer.validated_data
        serializer.instance = services.create_contract(
            staff_id=data["staff"].pk,
            contract_type=data["contract_type"],
            position=data["position"],
            start_date=data["start_date"],
            end_date=data.get("end_date"),
            basic_salary=data["basic_salary"],
            currency=data.get("currency"),
            actor=self.request.user,
        )

    @extend_schema(
        summary="End a contract", request=EndContractSerializer, responses={200: ContractSerializer}
    )
    @action(detail=True, methods=["post"])
    def end(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("hr.change_contract"):
            return Response(
                error_envelope("permission_denied", "You may not end contracts."), status=403
            )
        serializer = EndContractSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contract = services.end_contract(
            self.get_object(), end_date=serializer.validated_data["end_date"], actor=request.user
        )
        return Response(ContractSerializer(contract).data)


class LeaveRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """Any staff member may request their own leave — there is deliberately
    no `hr.add_leaverequest` permission gating it, since that would mean
    listing every staff-holding role here instead of just checking "is this
    a real member of staff". Endorsing and deciding are the actual controls."""

    queryset = LeaveRequest.objects.select_related("staff", "staff__user", "staff__department")
    serializer_class = LeaveRequestSerializer
    permission_classes = [HasModulePermission]
    required_permission = None
    filterset_fields = ["staff", "leave_type", "status"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_superuser or user.has_role(*UNSCOPED_ROLES):
            return queryset
        if user.has_role("hod"):
            profile = getattr(user, "staff_profile", None)
            if profile is not None and profile.department_id is not None:
                return queryset.filter(staff__department_id=profile.department_id)
            return queryset.none()
        profile = getattr(user, "staff_profile", None)
        if profile is not None:
            return queryset.filter(staff_id=profile.pk)
        return queryset.none()

    @extend_schema(
        summary="Request leave",
        request=SubmitLeaveRequestSerializer,
        responses={201: LeaveRequestSerializer},
    )
    @action(detail=False, methods=["post"])
    def submit(self, request: Request) -> Response:
        profile = getattr(request.user, "staff_profile", None)
        if profile is None:
            return Response(
                error_envelope("permission_denied", "Only a member of staff may request leave."),
                status=403,
            )
        serializer = SubmitLeaveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        leave_request = services.submit_leave_request(
            staff_id=profile.pk,
            leave_type=data["leave_type"],
            start_date=data["start_date"],
            end_date=data["end_date"],
            reason=data["reason"],
            actor=request.user,
        )
        return Response(LeaveRequestSerializer(leave_request).data, status=201)

    @extend_schema(
        summary="Endorse a leave request as its supervisor", responses={200: LeaveRequestSerializer}
    )
    @action(detail=True, methods=["post"])
    def endorse(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_role("hod"):
            return Response(
                error_envelope("permission_denied", "Only a department head may endorse leave."),
                status=403,
            )
        leave_request = services.endorse_leave_request(self.get_object(), actor=request.user)
        return Response(LeaveRequestSerializer(leave_request).data)

    @extend_schema(
        summary="HR's final decision on a leave request",
        request=DecideLeaveRequestSerializer,
        responses={200: LeaveRequestSerializer},
    )
    @action(detail=True, methods=["post"])
    def decide(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("hr.approve_leaverequest"):
            return Response(
                error_envelope("permission_denied", "You may not decide leave requests."),
                status=403,
            )
        serializer = DecideLeaveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        leave_request = services.decide_leave_request(
            self.get_object(), approve=data["approve"], actor=request.user, notes=data["notes"]
        )
        return Response(LeaveRequestSerializer(leave_request).data)

    def get_permissions(self):  # type: ignore[override]
        if self.action in {"submit", "endorse", "decide"}:
            return [IsAuthenticatedAndActive()]
        return super().get_permissions()


class AppraisalViewSet(viewsets.ModelViewSet):
    queryset = Appraisal.objects.select_related(
        "staff", "staff__user", "staff__department", "academic_year"
    )
    serializer_class = AppraisalSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "hr.view_appraisal",
        "POST": "hr.add_appraisal",
        "PUT": "hr.change_appraisal",
        "PATCH": "hr.change_appraisal",
    }
    filterset_fields = ["staff", "academic_year", "promotion_recommended"]

    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_superuser or user.has_role("hr", "ict_admin", "management"):
            return queryset
        if user.has_role("hod"):
            profile = getattr(user, "staff_profile", None)
            if profile is not None and profile.department_id is not None:
                return queryset.filter(staff__department_id=profile.department_id)
            return queryset.none()
        profile = getattr(user, "staff_profile", None)
        if profile is not None:
            return queryset.filter(staff_id=profile.pk)
        return queryset.none()

    def perform_create(self, serializer) -> None:
        data = serializer.validated_data
        serializer.instance = services.record_appraisal(
            staff_id=data["staff"].pk,
            academic_year_id=data["academic_year"].pk,
            rating=data["rating"],
            reviewer=self.request.user,
            comments=data.get("comments", ""),
            promotion_recommended=data.get("promotion_recommended", False),
            actor=self.request.user,
        )

    def perform_update(self, serializer) -> None:
        data = serializer.validated_data
        serializer.instance = services.update_appraisal(
            serializer.instance,
            rating=data.get("rating"),
            comments=data.get("comments"),
            promotion_recommended=data.get("promotion_recommended"),
            actor=self.request.user,
        )


class PayrollExportView(APIView):
    permission_classes = [HasModulePermission]
    required_permission = "hr.export_payroll"

    @extend_schema(
        summary="Payroll-ready export of active contracts",
        responses={200: PayrollRowSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        return Response(PayrollRowSerializer(services.payroll_export(), many=True).data)
