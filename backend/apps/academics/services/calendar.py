"""
Academic calendar queries (FR-ENR-01).

Modules ask the calendar whether an operation is permitted; they do not compare
dates themselves. One place decides "is registration open?", so extending a
registration window is a data change rather than a hunt through several modules
for date arithmetic.
"""

from __future__ import annotations

from datetime import datetime

from django.utils import timezone

from apps.academics.models import AcademicYear, Semester
from apps.core.exceptions import ConfigurationError, DomainError


class WindowClosed(DomainError):
    code = "window_closed"
    message = "The academic calendar does not permit this right now."
    status_code = 409


def current_year() -> AcademicYear | None:
    return AcademicYear.objects.filter(is_current=True).first()


def academic_year_name(academic_year_id: int) -> str:
    """The year's display name, e.g. "2026/2027".

    Exposed as a service so `registry` can build a student ID without importing
    academics models (ARCHITECTURE §4, rule 1). Raises `AcademicYear.DoesNotExist`
    if the id is unknown, which is the right outcome — a student cannot be admitted
    into an intake year that does not exist.
    """
    return AcademicYear.objects.values_list("name", flat=True).get(pk=academic_year_id)


def current_semester() -> Semester | None:
    return Semester.objects.filter(is_current=True).select_related("academic_year").first()


def require_current_semester() -> Semester:
    semester = current_semester()
    if semester is None:
        raise ConfigurationError(
            "No current semester is set. The registrar must mark one current "
            "before registration, attendance or grade entry can proceed."
        )
    return semester


def is_registration_open(semester: Semester | None = None, at: datetime | None = None) -> bool:
    """Whether course registration is open.

    An unset window means closed, not open. Defaulting to open would let students
    register in a semester nobody had configured yet.
    """
    semester = semester or current_semester()
    if semester is None:
        return False
    if semester.registration_opens is None or semester.registration_closes is None:
        return False

    now = at or timezone.now()
    return semester.registration_opens <= now <= semester.registration_closes


def is_add_drop_open(semester: Semester | None = None, at: datetime | None = None) -> bool:
    semester = semester or current_semester()
    if semester is None or semester.add_drop_closes is None:
        return False

    now = at or timezone.now()
    if semester.registration_opens and now < semester.registration_opens:
        return False
    return now <= semester.add_drop_closes


def is_exam_period(semester: Semester | None = None, at: datetime | None = None) -> bool:
    semester = semester or current_semester()
    if semester is None or semester.exam_start is None or semester.exam_end is None:
        return False

    today = (at or timezone.now()).date()
    return semester.exam_start <= today <= semester.exam_end


def require_registration_open(semester: Semester | None = None) -> Semester:
    """Raise unless registration is open. Used by Phase 2's registration flow."""
    semester = semester or require_current_semester()
    if not is_registration_open(semester):
        raise WindowClosed(
            f"Registration for {semester} is not open. "
            f"Window: {semester.registration_opens} – {semester.registration_closes}.",
            details={
                "semester": str(semester),
                "opens": (
                    semester.registration_opens.isoformat() if semester.registration_opens else None
                ),
                "closes": (
                    semester.registration_closes.isoformat()
                    if semester.registration_closes
                    else None
                ),
            },
        )
    return semester
