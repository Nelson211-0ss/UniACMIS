"""
Public service API for the registry.

Student creation and status changes go through here rather than through the ORM,
because each involves several things that must happen together: allocating a
non-reusable ID, opening the status history, and recording the audit entry.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.academics.services import calendar
from apps.core.exceptions import DomainError
from apps.core.services import holds as hold_services
from apps.registry.id_generation import generate_student_id
from apps.registry.models import Student, StudentDocument, StudentStatus, StudentStatusHistory

logger = logging.getLogger(__name__)


class InvalidStatusTransition(DomainError):
    code = "invalid_status_transition"
    message = "That status change is not allowed."


# A graduated or expelled record is terminal. Re-activating one would mean a
# second degree on the same record, or quietly reversing an expulsion without a
# new admission — both need a fresh admission, not an edit.
TERMINAL_STATUSES = frozenset({StudentStatus.GRADUATED, StudentStatus.EXPELLED})

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    StudentStatus.ACTIVE: frozenset(
        {
            StudentStatus.SUSPENDED,
            StudentStatus.DEFERRED,
            StudentStatus.WITHDRAWN,
            StudentStatus.GRADUATED,
            StudentStatus.EXPELLED,
        }
    ),
    StudentStatus.SUSPENDED: frozenset(
        {StudentStatus.ACTIVE, StudentStatus.WITHDRAWN, StudentStatus.EXPELLED}
    ),
    StudentStatus.DEFERRED: frozenset({StudentStatus.ACTIVE, StudentStatus.WITHDRAWN}),
    StudentStatus.WITHDRAWN: frozenset({StudentStatus.ACTIVE}),
    StudentStatus.GRADUATED: frozenset(),
    StudentStatus.EXPELLED: frozenset(),
}


@transaction.atomic
def create_student(
    *,
    programme_id: int,
    entry_academic_year_id: int,
    first_name: str,
    last_name: str,
    gender: str,
    actor: Any | None = None,
    student_id: str | None = None,
    reason: str = "",
    **extra: Any,
) -> Student:
    """Create a student record, allocating a student ID.

    `student_id` may be supplied when migrating legacy records that already carry
    a number; otherwise one is generated.
    """
    if not student_id:
        # Read through the academics *service*, not its models: the intake year's
        # name feeds the ID template, and that is the whole of what registry needs
        # to know about the academic calendar.
        year_name = calendar.academic_year_name(entry_academic_year_id)
        student_id = generate_student_id(programme_id, year_name)

    student = Student(
        student_id=student_id,
        programme_id=programme_id,
        entry_academic_year_id=entry_academic_year_id,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        gender=gender,
        admitted_on=extra.pop("admitted_on", None) or timezone.localdate(),
        **extra,
    )
    student.audit_reason = reason or "Student record created"
    student.full_clean()
    student.save()

    StudentStatusHistory.objects.create(
        student=student,
        from_status="",
        to_status=student.status,
        reason=reason or "Initial enrollment",
        effective_date=student.admitted_on or timezone.localdate(),
        changed_by=actor,
    )

    return student


@transaction.atomic
def change_status(
    student: Student,
    new_status: str,
    *,
    reason: str,
    actor: Any | None = None,
    effective_date: date | None = None,
    reference: str = "",
) -> Student:
    """Move a student to a new status, recording why (FR-REG-04)."""
    if not reason or not reason.strip():
        raise InvalidStatusTransition("A reason is required for every status change.")

    old_status = student.status

    if new_status == old_status:
        return student

    if old_status in TERMINAL_STATUSES:
        raise InvalidStatusTransition(
            f"{student.get_status_display()} is a final status. "
            "Admit the student again rather than editing this record.",
            details={"from": old_status, "to": new_status},
        )

    allowed = ALLOWED_TRANSITIONS.get(old_status, frozenset())
    if new_status not in allowed:
        raise InvalidStatusTransition(
            f"A student cannot go from {old_status} to {new_status}.",
            details={"from": old_status, "to": new_status, "allowed": sorted(allowed)},
        )

    effective = effective_date or timezone.localdate()

    student.status = new_status
    if new_status == StudentStatus.GRADUATED and student.graduated_on is None:
        student.graduated_on = effective
    student.audit_reason = reason
    student.full_clean()
    student.save()

    StudentStatusHistory.objects.create(
        student=student,
        from_status=old_status,
        to_status=new_status,
        reason=reason,
        effective_date=effective,
        changed_by=actor,
        reference=reference,
    )

    return student


def get_programme_id(student_id: int) -> int:
    """A student's current programme, without the caller importing `Student`.

    `enrollment` needs this to read the programme's credit limits (FR-ENR-02)
    — a service call rather than a model import, per the module boundary
    rules (ARCHITECTURE §4).
    """
    return Student.objects.values_list("programme_id", flat=True).get(pk=student_id)


def registration_holds(student_id: int) -> list[dict[str, Any]]:
    """Holds preventing this student from registering (FR-ENR-03).

    Resolved through the hold-provider registry, so the finance check works the
    same way whether it comes from the Phase 4 finance module or from the Phase 1
    stub.
    """
    return [
        {
            "code": hold.code,
            "message": hold.message,
            "source": hold.source,
            "blocking": hold.blocking,
            "details": hold.details,
        }
        for hold in hold_services.collect_holds(student_id)
    ]


def assert_can_register(student_id: int) -> None:
    """Raise if any blocking hold applies. Called by Phase 2's registration flow."""
    from apps.core.exceptions import BlockedByHold

    blocking = hold_services.blocking_holds(student_id)
    if blocking:
        raise BlockedByHold(
            "Registration is blocked until these are resolved.",
            details={
                "holds": [
                    {"code": h.code, "message": h.message, "source": h.source} for h in blocking
                ]
            },
        )


def attach_document(
    *,
    student: Student,
    document_type: str,
    title: str,
    file: Any,
    uploaded_by: Any | None = None,
    max_bytes: int | None = None,
) -> StudentDocument:
    """Store a document, capping the size and hashing the content.

    The hash is what makes verification meaningful: without it a verified
    certificate could be swapped for a different file afterwards and nobody would
    know.
    """
    from django.conf import settings

    limit = max_bytes or settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    size = getattr(file, "size", 0)

    if size > limit:
        raise ValidationError(
            {
                "file": (
                    f"This file is {size / 1024 / 1024:.1f} MB. The limit is "
                    f"{limit / 1024 / 1024:.0f} MB — uploads have to work on a slow link."
                )
            }
        )

    digest = hashlib.sha256()
    for chunk in file.chunks():
        digest.update(chunk)
    file.seek(0)

    return StudentDocument.objects.create(
        student=student,
        document_type=document_type,
        title=title,
        file=file,
        file_size=size,
        content_hash=digest.hexdigest(),
        uploaded_by=uploaded_by,
    )


def verify_document(
    document: StudentDocument, *, verified_by: Any, notes: str = ""
) -> StudentDocument:
    document.verified_by = verified_by
    document.verified_at = timezone.now()
    if notes:
        document.notes = notes
    document.save(update_fields=["verified_by", "verified_at", "notes"])
    return document
