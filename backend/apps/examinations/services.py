"""
Examinations services (FR-EXM-01…08).

`course_result` and `student_result` are the composition points: they trust
`enrollment` for which registrations exist and `core.services.holds` for
whether a result may be released, and reimplement neither. Attendance-based
exam eligibility (FR-ATT-02) is deliberately not re-checked here — it gates
whether a student may *sit* the exam, an operational decision the
examinations office and invigilators make against `attendance`'s own
eligibility endpoint before the sitting happens, not a rule about the mark
that results from it.
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.academics.services import grading
from apps.core.exceptions import ConfigurationError, DomainError
from apps.core.services.holds import blocking_holds
from apps.enrollment.services import (
    active_registration_ids,
    course_id_for_registration,
    registrations_for_student,
)
from apps.examinations.models import (
    AppealStatus,
    ApprovalStatus,
    Assessment,
    GradeAppeal,
    Mark,
    ResultApproval,
)
from apps.registry.services import get_programme_id

TWO_PLACES = Decimal("0.01")


class DroppedRegistration(DomainError):
    code = "dropped_registration"
    message = "This registration was dropped; marks cannot be entered against it."


class ReasonRequired(DomainError):
    code = "reason_required"


class AppealAlreadyDecided(DomainError):
    code = "appeal_already_decided"
    message = "This appeal has already been decided."
    status_code = 409


class InvalidApprovalTransition(DomainError):
    code = "invalid_approval_transition"
    status_code = 409


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------ assessments


@transaction.atomic
def create_assessment(
    *,
    course_id: int,
    name: str,
    weight_percent: Decimal,
    max_score: Decimal = Decimal("100"),
    sequence: int = 1,
    grade_entry_deadline: datetime | None = None,
    actor: Any = None,
) -> Assessment:
    assessment = Assessment(
        course_id=course_id,
        name=name,
        weight_percent=weight_percent,
        max_score=max_score,
        sequence=sequence,
        grade_entry_deadline=grade_entry_deadline,
    )
    assessment.audit_reason = "Assessment created"
    assessment.full_clean()
    assessment.save()
    return assessment


@transaction.atomic
def update_assessment(
    assessment: Assessment,
    *,
    name: str | None = None,
    weight_percent: Decimal | None = None,
    max_score: Decimal | None = None,
    sequence: int | None = None,
    grade_entry_deadline: datetime | Any = "__unset__",
    actor: Any = None,
) -> Assessment:
    if name is not None:
        assessment.name = name
    if weight_percent is not None:
        assessment.weight_percent = weight_percent
    if max_score is not None:
        assessment.max_score = max_score
    if sequence is not None:
        assessment.sequence = sequence
    if grade_entry_deadline != "__unset__":
        assessment.grade_entry_deadline = grade_entry_deadline
    assessment.audit_reason = "Assessment updated"
    assessment.full_clean()
    assessment.save()
    return assessment


def validate_assessment_weights(course_id: int) -> None:
    """A course's scheme must sum to exactly 100% before it can grade anyone
    — checked here, at the point a percentage is actually computed, rather
    than while a lecturer is still building the scheme up component by
    component."""
    weights = list(
        Assessment.objects.filter(course_id=course_id).values_list("weight_percent", flat=True)
    )
    if not weights:
        raise ConfigurationError("This course has no assessment scheme configured yet.")
    total = sum(weights)
    if total != Decimal("100"):
        raise ConfigurationError(
            f"This course's assessment weights sum to {total}%, not 100%. "
            "Fix the scheme before computing a result from it."
        )


# ------------------------------------------------------------------------ marks


@transaction.atomic
def record_mark(*, registration_id: int, assessment_id: int, score: Decimal, actor: Any) -> Mark:
    """FR-EXM-01, FR-EXM-02. Upserts — resubmitting a corrected score updates
    rather than duplicates, the same shape as `attendance.record_session`."""
    assessment = Assessment.objects.select_related("course").get(pk=assessment_id)

    mark = Mark.objects.filter(registration_id=registration_id, assessment_id=assessment_id).first()
    if mark is None:
        mark = Mark(registration_id=registration_id, assessment_id=assessment_id)
    # A registration that was dropped should never accumulate a mark, whether
    # this is its first mark or a correction to one entered before the drop.
    # The status string is compared directly rather than importing
    # `RegistrationStatus`, to keep this a service call away from
    # `enrollment`, not a model import.
    if mark.registration.status == "dropped":
        raise DroppedRegistration()

    mark.score = score
    mark.is_late = bool(
        assessment.grade_entry_deadline and timezone.now() > assessment.grade_entry_deadline
    )
    mark.entered_by = actor if getattr(actor, "pk", None) else None
    mark.audit_reason = "Mark recorded" + (" (late)" if mark.is_late else "")
    mark.full_clean()
    mark.save()
    return mark


@transaction.atomic
def moderate_mark(mark: Mark, *, moderated_score: Decimal, notes: str, actor: Any) -> Mark:
    if not notes.strip():
        raise ReasonRequired("A reason is required to moderate a mark.")
    mark.moderated_score = moderated_score
    mark.moderated_by = actor
    mark.moderation_notes = notes
    mark.audit_reason = f"Moderated: {notes}"
    mark.full_clean()
    mark.save()
    return mark


@transaction.atomic
def flag_irregularity(mark: Mark, *, notes: str, actor: Any) -> Mark:
    if not notes.strip():
        raise ReasonRequired("A reason is required to flag an irregularity.")
    mark.is_irregular = True
    mark.irregularity_notes = notes
    mark.audit_reason = f"Flagged irregular: {notes}"
    mark.full_clean()
    mark.save()
    return mark


@transaction.atomic
def clear_irregularity(mark: Mark, *, actor: Any, notes: str = "") -> Mark:
    mark.is_irregular = False
    mark.irregularity_notes = notes
    mark.audit_reason = "Irregularity cleared" + (f": {notes}" if notes else "")
    mark.full_clean()
    mark.save()
    return mark


def missing_marks_report(course_id: int, semester_id: int) -> list[dict[str, Any]]:
    """FR-EXM-08: every (registration, assessment) pair that should have a
    mark by now and does not."""
    registration_ids = active_registration_ids(course_id, semester_id)
    assessments = list(Assessment.objects.filter(course_id=course_id))
    if not registration_ids or not assessments:
        return []

    existing = set(
        Mark.objects.filter(
            registration_id__in=registration_ids, assessment__course_id=course_id
        ).values_list("registration_id", "assessment_id")
    )
    return [
        {"registration_id": rid, "assessment_id": a.pk, "assessment_name": a.name}
        for rid in sorted(registration_ids)
        for a in assessments
        if (rid, a.pk) not in existing
    ]


def course_result(registration_id: int) -> dict[str, Any]:
    """FR-EXM-04: the weighted percentage, letter grade and GPA point for one
    registration — `None` for the letter/point fields while any component is
    missing, the scheme is misconfigured, or a mark is under an irregularity
    flag, since a grade computed from an incomplete or disputed set of marks
    is worse than none at all."""
    course_id = course_id_for_registration(registration_id)
    assessments = (
        list(Assessment.objects.filter(course_id=course_id).order_by("sequence"))
        if course_id is not None
        else []
    )
    marks_by_assessment = {
        m.assessment_id: m
        for m in Mark.objects.filter(registration_id=registration_id).select_related("assessment")
    }

    configuration_error: str | None = None
    if assessments:
        try:
            validate_assessment_weights(course_id)
        except ConfigurationError as exc:
            configuration_error = exc.message

    components = []
    percent = Decimal("0")
    complete = bool(assessments) and configuration_error is None
    has_irregularity = False

    for assessment in assessments:
        mark = marks_by_assessment.get(assessment.pk)
        if mark is None:
            complete = False
            components.append(
                {
                    "assessment": assessment.name,
                    "weight_percent": assessment.weight_percent,
                    "score": None,
                }
            )
            continue
        if mark.is_irregular:
            has_irregularity = True
        fraction = (
            mark.effective_score / assessment.max_score if assessment.max_score else Decimal("0")
        )
        percent += _quantize(fraction * assessment.weight_percent)
        components.append(
            {
                "assessment": assessment.name,
                "weight_percent": assessment.weight_percent,
                "score": mark.effective_score,
                "max_score": assessment.max_score,
            }
        )

    result: dict[str, Any] = {
        "registration_id": registration_id,
        "components": components,
        "complete": complete,
        "has_irregularity": has_irregularity,
        "configuration_error": configuration_error,
        "percent": _quantize(percent) if assessments else None,
        "letter": None,
        "grade_point": None,
        "is_pass": None,
    }

    if complete and not has_irregularity:
        try:
            graded = grading.grade_for(result["percent"])
        except grading.GradingConfigurationError as exc:
            # No grading scale configured, or one with a gap — the same
            # "surface it, don't crash" treatment as a bad assessment scheme.
            result["complete"] = False
            result["configuration_error"] = str(exc)
        else:
            result["letter"] = graded.letter
            result["grade_point"] = graded.grade_point
            result["is_pass"] = graded.is_pass

    return result


def semester_gpa(student_id: int, semester_id: int) -> Decimal | None:
    """FR-EXM-04: the credit-weighted GPA over every complete, ungraded-free
    result the student has this semester."""
    entries = []
    for registration in registrations_for_student(student_id, semester_id):
        result = course_result(registration["registration_id"])
        if result["grade_point"] is not None:
            entries.append(
                grading.CourseGrade(
                    credit_hours=registration["credit_hours"], grade_point=result["grade_point"]
                )
            )
    return grading.gpa(entries)


# ------------------------------------------------------------- result approval


@transaction.atomic
def submit_for_approval(
    *, semester_id: int, programme_id: int | None, actor: Any
) -> ResultApproval:
    approval = ResultApproval.objects.filter(
        semester_id=semester_id, programme_id=programme_id
    ).first()
    if approval is None:
        approval = ResultApproval(semester_id=semester_id, programme_id=programme_id)
    elif approval.status not in {ApprovalStatus.PENDING, ApprovalStatus.REJECTED}:
        raise InvalidApprovalTransition(
            f"This approval is already {approval.status} and cannot be resubmitted."
        )
    approval.status = ApprovalStatus.PENDING
    approval.audit_reason = "Submitted for Senate approval"
    approval.full_clean()
    approval.save()
    return approval


@transaction.atomic
def approve_results(approval: ResultApproval, *, actor: Any, notes: str = "") -> ResultApproval:
    if approval.status != ApprovalStatus.PENDING:
        raise InvalidApprovalTransition(f"Cannot approve results that are {approval.status}.")
    approval.status = ApprovalStatus.APPROVED
    approval.approved_by = actor
    approval.approved_at = timezone.now()
    approval.approval_notes = notes
    approval.audit_reason = "Approved by Senate" + (f": {notes}" if notes else "")
    approval.full_clean()
    approval.save()
    return approval


@transaction.atomic
def reject_results(approval: ResultApproval, *, actor: Any, notes: str) -> ResultApproval:
    if not notes.strip():
        raise ReasonRequired("A reason is required to reject a set of results.")
    if approval.status != ApprovalStatus.PENDING:
        raise InvalidApprovalTransition(f"Cannot reject results that are {approval.status}.")
    approval.status = ApprovalStatus.REJECTED
    approval.approval_notes = notes
    approval.audit_reason = f"Rejected by Senate: {notes}"
    approval.full_clean()
    approval.save()
    return approval


@transaction.atomic
def publish_results(approval: ResultApproval, *, actor: Any) -> ResultApproval:
    if approval.status != ApprovalStatus.APPROVED:
        raise InvalidApprovalTransition(f"Cannot publish results that are {approval.status}.")
    approval.status = ApprovalStatus.PUBLISHED
    approval.published_by = actor
    approval.published_at = timezone.now()
    approval.audit_reason = "Published to students"
    approval.full_clean()
    approval.save()
    return approval


def _approval_for(student_id: int, semester_id: int) -> ResultApproval | None:
    programme_id = get_programme_id(student_id)
    return (
        ResultApproval.objects.filter(semester_id=semester_id, programme_id=programme_id).first()
        or ResultApproval.objects.filter(semester_id=semester_id, programme_id=None).first()
    )


def student_result(student_id: int, semester_id: int) -> dict[str, Any]:
    """FR-EXM-05, FR-EXM-06: what a student is shown. Published-but-withheld
    (an outstanding hold — arrears, discipline) says only that a result
    exists and is being withheld, never the marks themselves."""
    approval = _approval_for(student_id, semester_id)
    if approval is None or approval.status != ApprovalStatus.PUBLISHED:
        return {"published": False, "withheld": False, "courses": [], "gpa": None}

    holds = blocking_holds(student_id)
    if holds:
        return {
            "published": True,
            "withheld": True,
            "holds": [{"code": h.code, "message": h.message} for h in holds],
            "courses": [],
            "gpa": None,
        }

    courses = [
        {**course_result(r["registration_id"]), "course_id": r["course_id"]}
        for r in registrations_for_student(student_id, semester_id)
    ]
    return {
        "published": True,
        "withheld": False,
        "courses": courses,
        "gpa": semester_gpa(student_id, semester_id),
    }


# ---------------------------------------------------------------- grade appeals


@transaction.atomic
def submit_appeal(
    *, registration_id: int, assessment_id: int | None, reason: str, actor: Any
) -> GradeAppeal:
    if not reason.strip():
        raise ReasonRequired("A reason is required to submit an appeal.")
    appeal = GradeAppeal(
        registration_id=registration_id,
        assessment_id=assessment_id,
        reason=reason,
        submitted_by=actor if getattr(actor, "pk", None) else None,
    )
    appeal.audit_reason = "Appeal submitted"
    appeal.full_clean()
    appeal.save()
    return appeal


@transaction.atomic
def decide_appeal(appeal: GradeAppeal, *, decision: str, notes: str, actor: Any) -> GradeAppeal:
    if appeal.status not in {AppealStatus.SUBMITTED, AppealStatus.UNDER_REVIEW}:
        raise AppealAlreadyDecided()
    if decision not in {AppealStatus.UPHELD, AppealStatus.REJECTED}:
        raise DomainError("Decision must be 'upheld' or 'rejected'.", code="invalid_decision")
    if not notes.strip():
        raise ReasonRequired("A reason is required to decide an appeal.")

    appeal.status = decision
    appeal.decided_by = actor
    appeal.decision_notes = notes
    appeal.decided_at = timezone.now()
    appeal.audit_reason = f"Appeal {decision}: {notes}"
    appeal.full_clean()
    appeal.save()
    return appeal
