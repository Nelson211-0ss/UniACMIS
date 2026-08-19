from __future__ import annotations

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import error_envelope
from apps.core.permissions import HasModulePermission, IsAuthenticatedAndActive
from apps.documents import services
from apps.documents.models import IssuedDocument, TranscriptRequest
from apps.documents.serializers import (
    ClearanceStatusSerializer,
    DecideTranscriptRequestSerializer,
    IssueCertificateSerializer,
    IssuedDocumentSerializer,
    RequestTranscriptSerializer,
    RevokeDocumentSerializer,
    TranscriptRequestSerializer,
    VerificationResultSerializer,
)

UNSCOPED_ROLES = {"registrar", "ict_admin", "management"}


class TranscriptRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """A student sees only their own requests — the same self-service shape
    every other request-and-decide flow in this system uses."""

    queryset = TranscriptRequest.objects.select_related("student")
    serializer_class = TranscriptRequestSerializer
    permission_classes = [HasModulePermission]
    required_permission = None
    filterset_fields = ["student", "status"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_superuser or user.has_role(*UNSCOPED_ROLES):
            return queryset
        profile = getattr(user, "student_profile", None)
        if profile is not None:
            return queryset.filter(student_id=profile.pk)
        return queryset.none()

    @extend_schema(
        summary="Request a transcript",
        request=RequestTranscriptSerializer,
        responses={201: TranscriptRequestSerializer},
    )
    @action(detail=False, methods=["post"])
    def submit(self, request: Request) -> Response:
        serializer = RequestTranscriptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        on_behalf_of = data.get("student")
        if on_behalf_of is not None:
            if not request.user.has_perm("documents.add_transcriptrequest"):
                return Response(
                    error_envelope(
                        "permission_denied",
                        "You may not request a transcript on a student's behalf.",
                    ),
                    status=403,
                )
            student_id = on_behalf_of
        else:
            profile = getattr(request.user, "student_profile", None)
            if profile is None:
                return Response(
                    error_envelope(
                        "permission_denied", "Only a student may request their own transcript."
                    ),
                    status=403,
                )
            student_id = profile.pk

        transcript_request = services.request_transcript(
            student_id=student_id, reason=data.get("reason", ""), actor=request.user
        )
        return Response(TranscriptRequestSerializer(transcript_request).data, status=201)

    @extend_schema(
        summary="Decide a transcript request",
        request=DecideTranscriptRequestSerializer,
        responses={200: TranscriptRequestSerializer},
    )
    @action(detail=True, methods=["post"])
    def decide(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("documents.change_transcriptrequest"):
            return Response(
                error_envelope("permission_denied", "You may not decide transcript requests."),
                status=403,
            )
        serializer = DecideTranscriptRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        transcript_request = services.decide_transcript_request(
            self.get_object(), approve=data["approve"], actor=request.user, notes=data["notes"]
        )
        return Response(TranscriptRequestSerializer(transcript_request).data)

    def get_permissions(self):  # type: ignore[override]
        if self.action in {"submit", "decide"}:
            return [IsAuthenticatedAndActive()]
        return super().get_permissions()


class IssuedDocumentViewSet(viewsets.ReadOnlyModelViewSet):
    """A student sees only the documents issued in their own name."""

    queryset = IssuedDocument.objects.select_related("student")
    serializer_class = IssuedDocumentSerializer
    permission_classes = [HasModulePermission]
    required_permission = None
    filterset_fields = ["student", "document_type", "is_revoked"]
    ordering = ["-issued_at"]

    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_superuser or user.has_role(*UNSCOPED_ROLES):
            return queryset
        profile = getattr(user, "student_profile", None)
        if profile is not None:
            return queryset.filter(student_id=profile.pk)
        return queryset.none()

    @extend_schema(
        summary="Issue a certificate",
        request=IssueCertificateSerializer,
        responses={201: IssuedDocumentSerializer},
    )
    @action(detail=False, methods=["post"], url_path="issue-certificate")
    def issue_certificate(self, request: Request) -> Response:
        if not request.user.has_perm("documents.issue_certificate"):
            return Response(
                error_envelope("permission_denied", "You may not issue certificates."), status=403
            )
        serializer = IssueCertificateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        document = services.issue_certificate(
            student_id=data["student"],
            actor=request.user,
            override_reason=data.get("override_reason", ""),
        )
        return Response(IssuedDocumentSerializer(document).data, status=201)

    @extend_schema(
        summary="Revoke an issued document",
        request=RevokeDocumentSerializer,
        responses={200: IssuedDocumentSerializer},
    )
    @action(detail=True, methods=["post"])
    def revoke(self, request: Request, pk: str | None = None) -> Response:
        if not request.user.has_perm("documents.revoke_document"):
            return Response(
                error_envelope("permission_denied", "You may not revoke documents."), status=403
            )
        serializer = RevokeDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = services.revoke_document(
            self.get_object(), actor=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(IssuedDocumentSerializer(document).data)

    def get_permissions(self):  # type: ignore[override]
        if self.action in {"issue_certificate", "revoke"}:
            return [IsAuthenticatedAndActive()]
        return super().get_permissions()


class VerifyDocumentView(APIView):
    """FR-DOC-03. No login, rate-limited — the one page an employer reaches
    by scanning the QR code or typing the serial off a printed document."""

    permission_classes = [AllowAny]
    required_permission = None
    throttle_scope = "verification"

    @extend_schema(
        summary="Verify a document by its serial number",
        responses={200: VerificationResultSerializer},
    )
    def get(self, request: Request, serial_number: str) -> Response:
        result = services.verify_document(serial_number)
        if result is None:
            return Response(
                error_envelope("not_found", "No document with this serial number."), status=404
            )
        return Response(VerificationResultSerializer(result).data)


class GraduationClearanceView(APIView):
    """FR-DOC-04. A student checks their own clearance; staff check anyone's."""

    permission_classes = [HasModulePermission]
    required_permission = None

    @extend_schema(
        summary="Graduation clearance checklist", responses={200: ClearanceStatusSerializer}
    )
    def get(self, request: Request, student_id: int) -> Response:
        is_self = (
            hasattr(request.user, "student_profile")
            and request.user.student_profile.pk == student_id
        )
        if not is_self and not request.user.has_role(*UNSCOPED_ROLES):
            return Response(
                error_envelope("permission_denied", "You may not view this clearance status."),
                status=403,
            )
        return Response(
            ClearanceStatusSerializer(services.graduation_clearance_status(student_id)).data
        )
