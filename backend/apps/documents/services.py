"""Documents & certification services (FR-DOC-01…04)."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BlockedByHold, DomainError
from apps.core.services.holds import blocking_holds, collect_holds
from apps.documents.id_generation import generate_serial_number
from apps.documents.models import (
    DocumentType,
    IssuedDocument,
    TranscriptRequest,
    TranscriptRequestStatus,
)


class ReasonRequired(DomainError):
    code = "reason_required"


class InvalidTranscriptRequestTransition(DomainError):
    code = "invalid_transcript_request_transition"
    status_code = 409


class AlreadyIssued(DomainError):
    code = "already_issued"
    status_code = 409


@transaction.atomic
def request_transcript(
    *, student_id: int, reason: str = "", actor: Any = None
) -> TranscriptRequest:
    request = TranscriptRequest(student_id=student_id, reason=reason)
    request.audit_reason = "Transcript requested"
    request.full_clean()
    request.save()
    return request


@transaction.atomic
def decide_transcript_request(
    request: TranscriptRequest, *, approve: bool, actor: Any, notes: str
) -> TranscriptRequest:
    """Approving and issuing are the same act — there is no meaningful gap
    between "this transcript request is approved" and "the document
    exists"."""
    if not notes.strip():
        raise ReasonRequired("A reason is required to decide a transcript request.")
    if request.status != TranscriptRequestStatus.REQUESTED:
        raise InvalidTranscriptRequestTransition(f"This request is already {request.status}.")

    request.decided_by = actor
    request.decision_notes = notes
    request.decided_at = timezone.now()

    if approve:
        request.status = TranscriptRequestStatus.ISSUED
        request.audit_reason = f"Approved and issued: {notes}"
        request.full_clean()
        request.save()
        _issue(
            student_id=request.student_id,
            document_type=DocumentType.TRANSCRIPT,
            transcript_request=request,
            actor=actor,
        )
    else:
        request.status = TranscriptRequestStatus.REJECTED
        request.audit_reason = f"Rejected: {notes}"
        request.full_clean()
        request.save()
    return request


@transaction.atomic
def issue_certificate(*, student_id: int, actor: Any, override_reason: str = "") -> IssuedDocument:
    """FR-DOC-04: gated by graduation clearance, the same override shape
    `enrollment.register_course` uses for a fee hold — an override is only
    ever something the caller explicitly asks for by supplying a reason,
    never inferred just because the actor holds the permission."""
    blocking = blocking_holds(student_id)
    if blocking:
        attempting_override = bool(override_reason.strip())
        can_override = attempting_override and bool(
            actor and actor.has_perm("documents.override_clearance")
        )
        if not can_override:
            raise BlockedByHold(
                details={"holds": [{"code": h.code, "message": h.message} for h in blocking]}
            )

    return _issue(
        student_id=student_id,
        document_type=DocumentType.CERTIFICATE,
        actor=actor,
        override_reason=override_reason if blocking else "",
    )


def _issue(
    *,
    student_id: int,
    document_type: str,
    actor: Any = None,
    transcript_request: TranscriptRequest | None = None,
    override_reason: str = "",
) -> IssuedDocument:
    year = str(timezone.localdate().year)
    document = IssuedDocument(
        student_id=student_id,
        document_type=document_type,
        transcript_request=transcript_request,
        serial_number=generate_serial_number(document_type, year),
        issued_by=actor if getattr(actor, "pk", None) else None,
        issued_at=timezone.now(),
        override_reason=override_reason,
    )
    document.audit_reason = "Document issued" + (
        f" (override: {override_reason})" if override_reason else ""
    )
    document.full_clean()
    document.save()
    return document


@transaction.atomic
def revoke_document(document: IssuedDocument, *, actor: Any, reason: str) -> IssuedDocument:
    if not reason.strip():
        raise ReasonRequired("A reason is required to revoke a document.")
    if document.is_revoked:
        raise AlreadyIssued("This document is already revoked.")
    document.is_revoked = True
    document.revoked_reason = reason
    document.revoked_at = timezone.now()
    document.audit_reason = f"Revoked: {reason}"
    document.full_clean()
    document.save()
    return document


def verify_document(serial_number: str) -> dict[str, Any] | None:
    """FR-DOC-03: what a public, unauthenticated verifier is shown — enough
    to confirm authenticity, nothing a transcript or certificate itself
    would reveal (no grades, no fees)."""
    document = (
        IssuedDocument.objects.select_related("student").filter(serial_number=serial_number).first()
    )
    if document is None:
        return None
    return {
        "serial_number": document.serial_number,
        "document_type": document.document_type,
        "student_name": document.student.get_full_name(),
        "issued_at": document.issued_at,
        "is_valid": document.is_valid,
    }


def graduation_clearance_status(student_id: int) -> dict[str, Any]:
    """FR-DOC-04, reusing the same hold-provider registry that gates
    registration (FR-ENR-03) and result publication (FR-EXM-06) — a
    clearance checklist is the same question asked at a different moment."""
    holds = collect_holds(student_id)
    return {
        "clear": not any(h.blocking for h in holds),
        "holds": [
            {"code": h.code, "message": h.message, "source": h.source, "blocking": h.blocking}
            for h in holds
        ],
    }
