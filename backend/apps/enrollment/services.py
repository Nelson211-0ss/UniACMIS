"""
Public service API for enrollment.

`register_course` is the one function that pulls every Phase 1 mechanism
together into a single real workflow: the academic calendar decides *when*
(FR-ENR-01), curriculum's prerequisite and credit-limit checks decide *what*
(FR-ENR-02), and the hold-provider registry decides *whether at all*
(FR-ENR-03) — none of it reimplemented here, all of it called.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.academics.services import calendar
from apps.core.exceptions import BlockedByHold, DomainError
from apps.core.services import holds as hold_services
from apps.curriculum.services import credit_limits, total_credits, unmet_prerequisites
from apps.enrollment.models import CourseRegistration, RegistrationStatus
from apps.registry.services import get_programme_id

logger = logging.getLogger(__name__)


class PrerequisiteNotMet(DomainError):
    code = "prerequisite_not_met"
    message = "One or more prerequisites for this course have not been met."
    status_code = 409


class CreditLimitExceeded(DomainError):
    code = "credit_limit_exceeded"
    message = "This registration would exceed the programme's credit limit for the semester."
    status_code = 409


class AlreadyRegistered(DomainError):
    code = "already_registered"
    message = "This student is already registered for this course this semester."


class RegistrationNotOpen(DomainError):
    code = "registration_not_open"
    message = "Registration cannot be changed once completed."


def _resolve_semester(semester_id: int | None) -> Any:
    if semester_id is not None:
        return calendar.get_semester(semester_id)
    return calendar.require_current_semester()


def _passed_course_ids(student_id: int) -> dict[int, None]:
    """Courses this student has a COMPLETED registration for.

    None as the value, not a grade point: no grading exists until Phase 3, so a
    prerequisite's minimum-grade-point clause is unverifiable today and
    `unmet_prerequisites` already treats an unknown grade as satisfied rather
    than blocking on data that cannot exist yet.
    """
    course_ids = CourseRegistration.objects.filter(
        student_id=student_id, status=RegistrationStatus.COMPLETED
    ).values_list("course_id", flat=True)
    return dict.fromkeys(course_ids)


def _active_credit_load(student_id: int, semester_id: int, exclude_pk: int | None = None) -> int:
    queryset = CourseRegistration.objects.filter(
        student_id=student_id, semester_id=semester_id, status=RegistrationStatus.REGISTERED
    ).select_related("course")
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    return sum(registration.course.credit_hours for registration in queryset)


@transaction.atomic
def register_course(
    *,
    student_id: int,
    course_id: int,
    semester_id: int | None = None,
    actor: Any,
    override_reason: str = "",
) -> CourseRegistration:
    """FR-ENR-01…03. Raises the specific `DomainError` subclass for whichever
    rule blocked the registration, so a caller (or a test) can tell a closed
    calendar apart from an unmet prerequisite apart from a fee hold."""
    semester = _resolve_semester(semester_id)
    calendar.require_registration_open(semester)

    existing = CourseRegistration.objects.filter(
        student_id=student_id, course_id=course_id, semester_id=semester.pk
    ).first()
    if existing is not None and existing.status == RegistrationStatus.REGISTERED:
        raise AlreadyRegistered(details={"registration_id": existing.pk})
    if existing is not None and existing.status == RegistrationStatus.COMPLETED:
        raise RegistrationNotOpen("This course was already completed in this semester.")

    course_credit_hours = total_credits([course_id])
    programme_id = get_programme_id(student_id)

    unmet = unmet_prerequisites([course_id], _passed_course_ids(student_id))
    if unmet:
        raise PrerequisiteNotMet(
            details={
                "unmet": [
                    {
                        "course": u.course_code,
                        "requires": u.required_course_code,
                        "reason": u.reason,
                    }
                    for u in unmet
                ]
            }
        )

    _, max_credits = credit_limits(programme_id)
    projected_load = _active_credit_load(
        student_id, semester.pk, exclude_pk=existing.pk if existing else None
    )
    projected_load += course_credit_hours
    if projected_load > max_credits:
        raise CreditLimitExceeded(details={"max_credits": max_credits, "would_be": projected_load})

    blocking = hold_services.blocking_holds(student_id)
    if blocking:
        # An override is something the caller explicitly asks for by supplying a
        # reason — never something inferred just because the actor happens to
        # hold the permission. A plain registration attempt must behave
        # identically for a registrar and for anyone else: blocked. Only a
        # request that actually supplies a reason is treated as an override
        # attempt at all, and that attempt still needs the permission to succeed.
        attempting_override = bool(override_reason.strip())
        can_override = attempting_override and bool(
            actor and actor.has_perm("enrollment.override_hold")
        )
        if not can_override:
            raise BlockedByHold(
                details={"holds": [{"code": h.code, "message": h.message} for h in blocking]}
            )

    is_repeat = (
        CourseRegistration.objects.filter(student_id=student_id, course_id=course_id)
        .exclude(pk=existing.pk if existing else None)
        .exists()
    )

    if existing is not None:
        registration = existing
        registration.status = RegistrationStatus.REGISTERED
        registration.dropped_at = None
    else:
        registration = CourseRegistration(
            student_id=student_id, course_id=course_id, semester=semester
        )

    registration.is_repeat = is_repeat
    registration.registered_by = actor if getattr(actor, "pk", None) else None
    if blocking:
        registration.hold_override_by = actor
        registration.override_reason = override_reason
    registration.audit_reason = (
        f"Registered (override: {override_reason})" if blocking else "Registered"
    )
    registration.full_clean()
    registration.save()
    return registration


@transaction.atomic
def drop_course(
    registration: CourseRegistration, *, reason: str, actor: Any | None = None
) -> CourseRegistration:
    """FR-ENR-01: dropping is itself bound by the add/drop window, not just
    registering — a student cannot walk away from a course after the deadline
    the same way they could add one."""
    if not reason.strip():
        raise DomainError("A reason is required to drop a course.", code="reason_required")
    if registration.status != RegistrationStatus.REGISTERED:
        raise RegistrationNotOpen(f"Cannot drop a registration that is {registration.status}.")

    semester = registration.semester
    if not calendar.is_add_drop_open(semester):
        raise RegistrationNotOpen(
            "The add/drop window for this semester has closed.",
            details={"semester": str(semester)},
        )

    registration.status = RegistrationStatus.DROPPED
    registration.dropped_at = timezone.now()
    registration.drop_reason = reason
    registration.audit_reason = reason
    registration.full_clean()
    registration.save()
    return registration


@transaction.atomic
def record_prior_completion(
    registration: CourseRegistration, *, actor: Any, reason: str
) -> CourseRegistration:
    """Registrar-only stand-in for a completed course, ahead of Phase 3's real
    grading and result-publication workflow. Its purpose today is narrow:
    recognising transfer credit (FR-REG-05) and letting a prerequisite chain
    be demonstrated without pretending a grading system exists yet."""
    if not reason.strip():
        raise DomainError("A reason is required to record a completion.", code="reason_required")
    if registration.status == RegistrationStatus.COMPLETED:
        return registration

    registration.status = RegistrationStatus.COMPLETED
    registration.completed_by = actor
    registration.completed_at = timezone.now()
    registration.audit_reason = reason
    registration.full_clean()
    registration.save()
    return registration


def active_registration_ids(course_id: int, semester_id: int) -> set[int]:
    """Which registrations currently expect to be in this class.

    Attendance (FR-ATT-01) and, later, grade entry key off the registration
    id rather than the student id: a repeat's record must never be conflated
    with the original attempt's, which is exactly what `is_repeat` exists to
    distinguish elsewhere in this module.
    """
    return set(
        CourseRegistration.objects.filter(
            course_id=course_id, semester_id=semester_id, status=RegistrationStatus.REGISTERED
        ).values_list("pk", flat=True)
    )


def student_id_for_registration(registration_id: int) -> int | None:
    """Whose registration this is — so a caller can answer "is this mine?"
    (FR-ATT-02's eligibility check, and its own record's summary) without
    importing `CourseRegistration` to look it up."""
    return (
        CourseRegistration.objects.filter(pk=registration_id)
        .values_list("student_id", flat=True)
        .first()
    )


def course_id_for_registration(registration_id: int) -> int | None:
    """The course a registration is for, without importing `CourseRegistration`
    to look it up — `examinations` needs this to find a course's assessment
    scheme from a registration id alone."""
    return (
        CourseRegistration.objects.filter(pk=registration_id)
        .values_list("course_id", flat=True)
        .first()
    )


def registrations_for_student(student_id: int, semester_id: int) -> list[dict[str, Any]]:
    """Every registration a student holds in a semester, with the course
    fields a result computation needs — a transcript is built one semester's
    registrations at a time (FR-EXM-04)."""
    return [
        {
            "registration_id": r.pk,
            "course_id": r.course_id,
            "credit_hours": r.course.credit_hours,
            "is_repeat": r.is_repeat,
            "status": r.status,
        }
        for r in CourseRegistration.objects.filter(
            student_id=student_id, semester_id=semester_id
        ).select_related("course")
    ]


def class_list(course_id: int, semester_id: int) -> list[dict[str, Any]]:
    """FR-ENR-04. Ordered for a printable register, not by database id."""
    registrations = (
        CourseRegistration.objects.filter(
            course_id=course_id, semester_id=semester_id, status=RegistrationStatus.REGISTERED
        )
        .select_related("student")
        .order_by("student__last_name", "student__first_name")
    )
    return [
        {
            "registration_id": r.pk,
            "student_id": r.student.student_id,
            "full_name": r.student.get_full_name(),
            "is_repeat": r.is_repeat,
        }
        for r in registrations
    ]


def credit_summary(student_id: int, semester_id: int) -> dict[str, Any]:
    programme_id = get_programme_id(student_id)
    min_credits, max_credits = credit_limits(programme_id)
    load = _active_credit_load(student_id, semester_id)
    return {
        "registered_credits": load,
        "min_credits": min_credits,
        "max_credits": max_credits,
        "meets_minimum": load >= min_credits,
    }
