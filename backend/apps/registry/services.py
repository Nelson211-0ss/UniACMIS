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
from django.db.models import Count
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


def _resolve_import_row(row: dict[str, str]) -> tuple[dict[str, Any] | None, dict[str, str]]:
    """Resolves the natural keys a legacy spreadsheet actually has —
    programme code, academic year name, curriculum version — and validates
    the row without writing anything or allocating a real student ID for a
    row that might never be committed."""
    from apps.academics.services.calendar import academic_year_id_for_name
    from apps.curriculum.services import curriculum_version_id_for, programme_id_for_code

    errors: dict[str, str] = {}
    kwargs: dict[str, Any] = {}

    for field in ("first_name", "last_name", "gender"):
        value = (row.get(field) or "").strip()
        if not value:
            errors[field] = "Required."
        else:
            kwargs[field] = value

    programme_code = (row.get("programme_code") or "").strip()
    programme_id = programme_id_for_code(programme_code) if programme_code else None
    if programme_id is None:
        errors["programme_code"] = f"No programme with code '{programme_code}'."
    else:
        kwargs["programme_id"] = programme_id

    year_name = (row.get("entry_academic_year") or "").strip()
    academic_year_id = academic_year_id_for_name(year_name) if year_name else None
    if academic_year_id is None:
        errors["entry_academic_year"] = f"No academic year named '{year_name}'."
    else:
        kwargs["entry_academic_year_id"] = academic_year_id

    version = (row.get("curriculum_version") or "").strip()
    if version:
        curriculum_version_id = (
            curriculum_version_id_for(programme_id=programme_id, version=version)
            if programme_id is not None
            else None
        )
        if curriculum_version_id is None:
            errors["curriculum_version"] = (
                f"No curriculum version '{version}' for '{programme_code}'."
            )
        else:
            kwargs["curriculum_version_id"] = curriculum_version_id

    for field in (
        "student_id",
        "middle_name",
        "date_of_birth",
        "national_id_number",
        "state_of_origin",
        "nationality",
        "phone",
        "email",
        "disability_details",
    ):
        if row.get(field):
            kwargs[field] = row[field].strip()

    if row.get("has_disability"):
        kwargs["has_disability"] = row["has_disability"].strip().lower() in ("1", "true", "yes")

    if errors:
        return None, errors

    candidate = Student(
        admitted_on=timezone.localdate(),
        **{k: v for k, v in kwargs.items() if k not in ("student_id",)},
        student_id=kwargs.get("student_id") or "PENDING",
    )
    try:
        candidate.full_clean(exclude=[] if kwargs.get("student_id") else ["student_id"])
    except ValidationError as exc:
        return None, {field: "; ".join(messages) for field, messages in exc.message_dict.items()}

    return kwargs, {}


@transaction.atomic
def import_students(
    rows: list[dict[str, str]], *, commit: bool, actor: Any = None, reason: str = ""
) -> dict[str, Any]:
    """NFR-DATA-03: bulk-imports legacy student records with validation and
    rollback. `commit=False` is a dry run that writes nothing, for previewing
    what a batch would do. `commit=True` writes only if every row validates —
    a batch half-imported because row 400 of 500 turned out invalid is worse
    than a clean reject-and-retry, so this is all-or-nothing: the database
    transaction itself is the rollback mechanism the requirement asks for.
    """
    resolved: list[tuple[int, dict[str, Any]]] = []
    errors: list[dict[str, Any]] = []

    for index, row in enumerate(rows, start=1):
        kwargs, row_errors = _resolve_import_row(row)
        if row_errors:
            errors.append({"row": index, "errors": row_errors})
        else:
            resolved.append((index, kwargs))

    # A DB uniqueness check can only ever catch a clash against an already-saved
    # row — two rows in the same not-yet-committed batch both claiming the same
    # legacy id would otherwise sail through per-row validation and only blow up
    # as a raw IntegrityError partway through the commit loop below.
    seen_student_ids: dict[str, int] = {}
    for index, kwargs in resolved:
        supplied = kwargs.get("student_id")
        if not supplied:
            continue
        if supplied in seen_student_ids:
            errors.append(
                {
                    "row": index,
                    "errors": {"student_id": f"Duplicate of row {seen_student_ids[supplied]}."},
                }
            )
        else:
            seen_student_ids[supplied] = index
    resolved = [
        (index, kwargs)
        for index, kwargs in resolved
        if not kwargs.get("student_id") or seen_student_ids[kwargs["student_id"]] == index
    ]

    if errors or not commit:
        return {"total": len(rows), "valid": len(resolved), "created": 0, "errors": errors}

    created = [
        create_student(actor=actor, reason=reason or "Bulk legacy import", **kwargs).pk
        for _index, kwargs in resolved
    ]
    return {"total": len(rows), "valid": len(resolved), "created": len(created), "errors": []}


def get_programme_id(student_id: int) -> int:
    """A student's current programme, without the caller importing `Student`.

    `enrollment` needs this to read the programme's credit limits (FR-ENR-02)
    — a service call rather than a model import, per the module boundary
    rules (ARCHITECTURE §4).
    """
    return Student.objects.values_list("programme_id", flat=True).get(pk=student_id)


def residency_for_student(student_id: int) -> str:
    """`local` or `international` (FR-FIN-01's fee-structure dimension),
    derived from nationality rather than stored as its own flag — the two
    have never disagreed in practice, and a second field would just be a
    second place for them to drift apart."""
    from apps.core.choices import Residency

    nationality = Student.objects.values_list("nationality", flat=True).get(pk=student_id)
    return Residency.LOCAL if nationality == "South Sudanese" else Residency.INTERNATIONAL


def sponsor_id_for_student(student_id: int) -> int | None:
    """The sponsoring organisation on record, if any (FR-FIN-04) — a service
    call rather than a `Student` import, per the module boundary rules."""
    return Student.objects.values_list("sponsor_id", flat=True).get(pk=student_id)


def current_level_for_student(student_id: int) -> int:
    """A student's year of study, for the fee structure it selects
    (FR-FIN-01) — a service call rather than a `Student` import."""
    return Student.objects.values_list("current_level", flat=True).get(pk=student_id)


def gender_for_student(student_id: int) -> str:
    """A student's declared gender (`FR-HOS-02`'s single-sex room matching)
    — a service call rather than a `Student` import."""
    return Student.objects.values_list("gender", flat=True).get(pk=student_id)


def hostel_priority_profile(student_ids: list[int]) -> list[dict[str, Any]]:
    """The fields `hostel`'s waiting-list ranking needs, for a whole batch at
    once (`FR-HOS-02`) — one query rather than one per candidate, and a
    service call rather than a `Student` import."""
    return list(
        Student.objects.filter(pk__in=student_ids).values(
            "id", "has_disability", "state_of_origin", "entry_academic_year_id"
        )
    )


def is_graduated(student_id: int) -> bool:
    """`alumni` needs to confirm a student has actually graduated before a
    profile is created for them — a service call rather than a `Student`
    import, and a boolean rather than `StudentStatus` itself so the caller
    never needs that vocabulary at all."""
    status = Student.objects.values_list("status", flat=True).get(pk=student_id)
    return status == StudentStatus.GRADUATED


def active_student_contacts(*, programme_id: int | None = None) -> list[dict[str, Any]]:
    """Phone/email for every active student, optionally narrowed to one
    programme — the audience `communications.send_announcement` fans out
    to, without it importing `Student`."""
    queryset = Student.objects.filter(status=StudentStatus.ACTIVE)
    if programme_id is not None:
        queryset = queryset.filter(programme_id=programme_id)
    return list(queryset.values("id", "phone", "email"))


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


def enrollment_counts(*, academic_year_id: int | None = None) -> dict[str, Any]:
    """FR-RPT-01/03: active enrollment disaggregated by gender, disability
    and state of origin — the report the constrained choices Phase 1
    captured (rather than free text) exist to make possible."""
    queryset = Student.objects.filter(status=StudentStatus.ACTIVE)
    if academic_year_id is not None:
        queryset = queryset.filter(entry_academic_year_id=academic_year_id)

    def _counts(field: str) -> dict[str, int]:
        rows = queryset.values(field).annotate(count=Count("id")).order_by(field)
        return {row[field]: row["count"] for row in rows}

    return {
        "total": queryset.count(),
        "by_gender": _counts("gender"),
        "by_disability": {
            "with_disability": queryset.filter(has_disability=True).count(),
            "without_disability": queryset.filter(has_disability=False).count(),
        },
        "by_state_of_origin": _counts("state_of_origin"),
        "by_programme": _counts("programme_id"),
    }


def student_register(*, academic_year_id: int | None = None) -> list[dict[str, Any]]:
    """FR-RPT-02: one row per active student, the raw disaggregated listing
    a statutory return is built from — a generic export rather than a
    guess at MoHEST's actual template, which is an open item (see
    `docs/TRACEABILITY.md`)."""
    queryset = Student.objects.filter(status=StudentStatus.ACTIVE).select_related("programme")
    if academic_year_id is not None:
        queryset = queryset.filter(entry_academic_year_id=academic_year_id)
    return [
        {
            "student_number": student.student_id,
            "name": student.get_full_name(),
            "gender": student.gender,
            "has_disability": student.has_disability,
            "state_of_origin": student.state_of_origin,
            "programme": student.programme.name,
            "level": student.current_level,
        }
        for student in queryset.order_by("programme_id", "last_name")
    ]


def staff_student_ratio() -> dict[str, Any]:
    """FR-RPT-01's "ratios" — active students per active member of staff."""
    from apps.registry.models import StaffProfile

    student_count = Student.objects.filter(status=StudentStatus.ACTIVE).count()
    staff_count = StaffProfile.objects.filter(is_active=True).count()
    ratio = (student_count / staff_count) if staff_count else None
    return {"students": student_count, "staff": staff_count, "students_per_staff": ratio}
