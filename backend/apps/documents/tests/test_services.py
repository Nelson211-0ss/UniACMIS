"""Documents & certification service layer (FR-DOC-01…04)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.core.exceptions import BlockedByHold
from apps.core.providers.holds import set_demo_balance
from apps.documents import services
from apps.documents.models import DocumentType, TranscriptRequestStatus

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------- transcripts


def test_requesting_a_transcript(student):
    request = services.request_transcript(student_id=student.pk, reason="Job application")
    assert request.status == TranscriptRequestStatus.REQUESTED


def test_deciding_requires_notes(student):
    request = services.request_transcript(student_id=student.pk)
    with pytest.raises(services.ReasonRequired):
        services.decide_transcript_request(request, approve=True, actor=None, notes=" ")


def test_approving_issues_the_document_in_the_same_step(student, registrar):
    request = services.request_transcript(student_id=student.pk)
    decided = services.decide_transcript_request(
        request, approve=True, actor=registrar, notes="Verified, no holds"
    )
    assert decided.status == TranscriptRequestStatus.ISSUED
    issued = decided.issued_documents.get()
    assert issued.document_type == DocumentType.TRANSCRIPT
    assert issued.serial_number.startswith("TRX/")


def test_rejecting_a_transcript_request(student, registrar):
    request = services.request_transcript(student_id=student.pk)
    decided = services.decide_transcript_request(
        request, approve=False, actor=registrar, notes="Outstanding fee balance"
    )
    assert decided.status == TranscriptRequestStatus.REJECTED
    assert not decided.issued_documents.exists()


def test_a_decided_request_cannot_be_decided_again(student, registrar):
    request = services.request_transcript(student_id=student.pk)
    services.decide_transcript_request(request, approve=True, actor=registrar, notes="Approved")
    with pytest.raises(services.InvalidTranscriptRequestTransition):
        services.decide_transcript_request(
            request, approve=True, actor=registrar, notes="Approved again"
        )


# -------------------------------------------------------------- certificates


def test_issuing_a_certificate_with_no_holds(student, registrar):
    document = services.issue_certificate(student_id=student.pk, actor=registrar)
    assert document.document_type == DocumentType.CERTIFICATE
    assert document.serial_number.startswith("CERT/")
    assert document.is_valid


def test_issuing_a_certificate_is_blocked_by_a_hold(student, registrar):
    set_demo_balance(student.pk, Decimal("50000"))
    with pytest.raises(BlockedByHold):
        services.issue_certificate(student_id=student.pk, actor=registrar)


def test_an_override_without_the_permission_still_blocks(student, hod):
    set_demo_balance(student.pk, Decimal("50000"))
    with pytest.raises(BlockedByHold):
        services.issue_certificate(
            student_id=student.pk, actor=hod, override_reason="Waived by dean"
        )


def test_an_override_with_the_permission_succeeds(student, registrar):
    set_demo_balance(student.pk, Decimal("50000"))
    document = services.issue_certificate(
        student_id=student.pk,
        actor=registrar,
        override_reason="Cleared by the finance office directly",
    )
    assert document.override_reason == "Cleared by the finance office directly"


def test_revoking_a_document_requires_a_reason(student, registrar):
    document = services.issue_certificate(student_id=student.pk, actor=registrar)
    with pytest.raises(services.ReasonRequired):
        services.revoke_document(document, actor=registrar, reason=" ")


def test_revoking_a_document_twice_is_rejected(student, registrar):
    document = services.issue_certificate(student_id=student.pk, actor=registrar)
    services.revoke_document(document, actor=registrar, reason="Issued in error")
    with pytest.raises(services.AlreadyIssued):
        services.revoke_document(document, actor=registrar, reason="Issued in error, again")


# --------------------------------------------------------------- verification


def test_verifying_an_unknown_serial_returns_none():
    assert services.verify_document("CERT/2020/99999") is None


def test_verifying_a_known_serial(student, registrar):
    document = services.issue_certificate(student_id=student.pk, actor=registrar)
    result = services.verify_document(document.serial_number)
    assert result["is_valid"] is True
    assert result["student_name"] == student.get_full_name()


def test_verifying_a_revoked_document_shows_it_is_invalid(student, registrar):
    document = services.issue_certificate(student_id=student.pk, actor=registrar)
    services.revoke_document(document, actor=registrar, reason="Printed in error")
    result = services.verify_document(document.serial_number)
    assert result["is_valid"] is False


# ------------------------------------------------------------------ clearance


def test_clearance_is_clear_with_no_holds(student):
    status = services.graduation_clearance_status(student.pk)
    assert status["clear"] is True
    assert status["holds"] == []


def test_clearance_reflects_a_blocking_hold(student):
    set_demo_balance(student.pk, Decimal("1000"))
    status = services.graduation_clearance_status(student.pk)
    assert status["clear"] is False
    assert any(h["blocking"] for h in status["holds"])
