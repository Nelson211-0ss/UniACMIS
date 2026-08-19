"""
Attendance services (FR-ATT-01…02).

`record_session` is the composition point: it trusts `enrollment` for who is
actually meant to be in the room and `timetabling` for which course/semester a
class slot belongs to, and reimplements neither.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import transaction

from apps.academics.services import config as academics_config
from apps.attendance.models import AttendanceStatus, AttendanceWaiver, SessionRecord
from apps.core.exceptions import DomainError
from apps.enrollment.services import active_registration_ids
from apps.timetabling.services import entry_context

TWO_PLACES = Decimal("0.01")


class UnregisteredStudent(DomainError):
    code = "unregistered_student"
    message = "One or more of these registrations are not active for this class."
    status_code = 400


class WaiverReasonRequired(DomainError):
    code = "reason_required"
    message = "A reason is required to waive the attendance threshold."


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@transaction.atomic
def record_session(
    *,
    timetable_entry_id: int,
    session_date: date,
    marks: list[dict[str, Any]],
    actor: Any,
) -> list[SessionRecord]:
    """FR-ATT-01. `marks` is `[{"registration_id": int, "status": str, "notes": str}, …]`
    — one entry per student the lecturer is marking in this sitting. Upserts,
    so re-submitting a corrected register (the common offline-sync case: the
    device queued the same session twice) updates rather than duplicates."""
    course_id, semester_id = entry_context(timetable_entry_id)
    valid_ids = active_registration_ids(course_id, semester_id)

    given_ids = {m["registration_id"] for m in marks}
    invalid = given_ids - valid_ids
    if invalid:
        raise UnregisteredStudent(details={"registration_ids": sorted(invalid)})

    records = []
    for mark in marks:
        record = SessionRecord.objects.filter(
            timetable_entry_id=timetable_entry_id,
            session_date=session_date,
            registration_id=mark["registration_id"],
        ).first()
        if record is None:
            record = SessionRecord(
                timetable_entry_id=timetable_entry_id,
                session_date=session_date,
                registration_id=mark["registration_id"],
            )
        record.status = mark.get("status", AttendanceStatus.PRESENT)
        record.notes = mark.get("notes", "")
        record.recorded_by = actor if getattr(actor, "pk", None) else None
        record.audit_reason = "Attendance recorded"
        record.full_clean()
        record.save()
        records.append(record)
    return records


def session_records(timetable_entry_id: int, session_date: date) -> list[SessionRecord]:
    return list(
        SessionRecord.objects.filter(
            timetable_entry_id=timetable_entry_id, session_date=session_date
        ).select_related("registration__student")
    )


def attendance_summary(registration_id: int) -> dict[str, Any]:
    """Sessions this registration has any record for are the denominator — a
    class that met but was never recorded is invisible to this calculation,
    the same way an ungraded course is invisible until someone enters a mark."""
    records = SessionRecord.objects.filter(registration_id=registration_id)
    total = records.exclude(status=AttendanceStatus.EXCUSED).count()
    attended = records.filter(status__in=[AttendanceStatus.PRESENT, AttendanceStatus.LATE]).count()
    percentage = _quantize(Decimal(attended) / Decimal(total) * 100) if total else None
    return {
        "sessions_recorded": total,
        "sessions_attended": attended,
        "percentage": percentage,
    }


def is_below_threshold(registration_id: int) -> bool:
    summary = attendance_summary(registration_id)
    if summary["percentage"] is None:
        return False
    return summary["percentage"] < academics_config.attendance_threshold()


def exam_eligibility(registration_id: int) -> dict[str, Any]:
    """FR-ATT-02. What `examinations` checks before letting a registration
    sit — below-threshold blocks unless a waiver was granted."""
    summary = attendance_summary(registration_id)
    below = is_below_threshold(registration_id)
    waived = AttendanceWaiver.objects.filter(registration_id=registration_id).exists()
    return {
        **summary,
        "threshold": academics_config.attendance_threshold(),
        "below_threshold": below,
        "waived": waived,
        "eligible": not below or waived,
    }


@transaction.atomic
def grant_waiver(registration_id: int, *, actor: Any, reason: str) -> AttendanceWaiver:
    if not reason.strip():
        raise WaiverReasonRequired()
    waiver = AttendanceWaiver.objects.filter(registration_id=registration_id).first()
    if waiver is None:
        waiver = AttendanceWaiver(registration_id=registration_id)
    waiver.granted_by = actor if getattr(actor, "pk", None) else None
    waiver.reason = reason
    waiver.audit_reason = reason
    waiver.full_clean()
    waiver.save()
    return waiver
