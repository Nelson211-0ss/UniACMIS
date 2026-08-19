from __future__ import annotations

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.exceptions import error_envelope
from apps.core.permissions import HasModulePermission, IsAuthenticatedAndActive
from apps.library import services
from apps.library.models import LibraryItem, Loan
from apps.library.serializers import (
    CheckoutSerializer,
    LibraryItemSerializer,
    LoanSerializer,
    WaiveFineSerializer,
)

UNSCOPED_ROLES = {"library", "ict_admin", "management"}


class LibraryItemViewSet(viewsets.ModelViewSet):
    """Browsing the catalogue needs no specific permission — it is not
    sensitive data — only cataloguing an item does."""

    queryset = LibraryItem.objects.all()
    serializer_class = LibraryItemSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "SAFE": None,
        "POST": "library.add_libraryitem",
        "PUT": "library.change_libraryitem",
        "PATCH": "library.change_libraryitem",
    }
    filterset_fields = ["item_type", "is_electronic", "is_active"]
    search_fields = ["title", "author", "isbn"]

    def perform_create(self, serializer) -> None:
        serializer.instance = services.create_library_item(
            actor=self.request.user, **serializer.validated_data
        )

    def perform_update(self, serializer) -> None:
        serializer.instance = services.update_library_item(
            serializer.instance, actor=self.request.user, **serializer.validated_data
        )


class LoanViewSet(viewsets.ReadOnlyModelViewSet):
    """A student or staff member sees their own loans without needing
    `library.view_loan` — the same "authenticated, queryset does the real
    narrowing" shape as `hr.LeaveRequestViewSet`. Every write is a librarian's
    named action, never a raw PATCH."""

    queryset = Loan.objects.select_related("item", "borrower_student", "borrower_staff")
    serializer_class = LoanSerializer
    permission_classes = [HasModulePermission]
    required_permission = None
    filterset_fields = ["item", "borrower_student", "borrower_staff", "status"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_superuser or user.has_role(*UNSCOPED_ROLES):
            return queryset
        if user.has_role("student"):
            return queryset.filter(borrower_student__user=user)
        profile = getattr(user, "staff_profile", None)
        if profile is not None:
            return queryset.filter(borrower_staff_id=profile.pk)
        return queryset.none()

    @extend_schema(
        summary="Check out an item", request=CheckoutSerializer, responses={201: LoanSerializer}
    )
    @action(detail=False, methods=["post"])
    def checkout(self, request: Request) -> Response:
        if not request.user.has_perm("library.add_loan"):
            return Response(
                error_envelope("permission_denied", "You may not check out items."), status=403
            )
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        loan = services.checkout_item(
            item_id=data["item"],
            borrower_student_id=data.get("borrower_student"),
            borrower_staff_id=data.get("borrower_staff"),
            due_date=data.get("due_date"),
            actor=request.user,
        )
        return Response(LoanSerializer(loan).data, status=201)

    @extend_schema(summary="Return an item", responses={200: LoanSerializer})
    @action(detail=True, methods=["post"], url_path="return-loan")
    def return_loan(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("library.change_loan"):
            return Response(
                error_envelope("permission_denied", "You may not record a return."), status=403
            )
        loan = services.return_item(self.get_object(), actor=request.user)
        return Response(LoanSerializer(loan).data)

    @extend_schema(summary="Report an item lost", responses={200: LoanSerializer})
    @action(detail=True, methods=["post"], url_path="mark-lost")
    def mark_lost(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("library.change_loan"):
            return Response(
                error_envelope("permission_denied", "You may not record a loss."), status=403
            )
        loan = services.mark_lost(self.get_object(), actor=request.user)
        return Response(LoanSerializer(loan).data)

    @extend_schema(
        summary="Waive an overdue fine",
        request=WaiveFineSerializer,
        responses={200: LoanSerializer},
    )
    @action(detail=True, methods=["post"], url_path="waive-fine")
    def waive_fine(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("library.waive_fine"):
            return Response(
                error_envelope("permission_denied", "You may not waive fines."), status=403
            )
        serializer = WaiveFineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        loan = services.waive_fine(
            self.get_object(), actor=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(LoanSerializer(loan).data)

    def get_permissions(self):  # type: ignore[override]
        if self.action in {"checkout", "return_loan", "mark_lost", "waive_fine"}:
            return [IsAuthenticatedAndActive()]
        return super().get_permissions()
