"""
Attendance service layer (FR-ATT-01…02): recording composes `enrollment` and
`timetabling` rather than re-checking a roster or a class slot itself; the
threshold and eligibility math is the part that is actually new here.
"""

from __future__ import annotations

from datetime import time, timedelta
from decimal import Decimal

import pytest

from apps.attendance import services
from apps.attendance.models import AttendanceStatus, SessionRecord
from apps.enrollment.services import register_course
from apps.timetabling.models import DayOfWeek
from apps.timetabling.services import create_entry

pytestmark = pytest.mark.django_db


@pytest.fixture
def entry(course, semester):
    return create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.MONDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        actor=None,
    )


@pytest.fixture
def registration(student, course, semester, registrar):
    return register_course(
        student_id=student.pk, course_id=course.pk, semester_id=semester.pk, actor=registrar
    )


def test_records_a_session_for_a_registered_student(entry, registration):
    records = services.record_session(
        timetable_entry_id=entry.pk,
        session_date=entry.semester.teaching_start,
        marks=[{"registration_id": registration.pk, "status": AttendanceStatus.PRESENT}],
        actor=None,
    )
    assert len(records) == 1
    assert records[0].status == AttendanceStatus.PRESENT


def test_resubmitting_a_session_corrects_rather_than_duplicates(entry, registration):
    session_date = entry.semester.teaching_start
    services.record_session(
        timetable_entry_id=entry.pk,
        session_date=session_date,
        marks=[{"registration_id": registration.pk, "status": AttendanceStatus.ABSENT}],
        actor=None,
    )
    services.record_session(
        timetable_entry_id=entry.pk,
        session_date=session_date,
        marks=[{"registration_id": registration.pk, "status": AttendanceStatus.PRESENT}],
        actor=None,
    )
    assert SessionRecord.objects.filter(registration=registration).count() == 1
    assert SessionRecord.objects.get(registration=registration).status == AttendanceStatus.PRESENT


def test_marking_an_unregistered_student_is_rejected(entry, registration, course, semester):
    with pytest.raises(services.UnregisteredStudent):
        services.record_session(
            timetable_entry_id=entry.pk,
            session_date=entry.semester.teaching_start,
            marks=[{"registration_id": registration.pk + 999, "status": AttendanceStatus.PRESENT}],
            actor=None,
        )


def test_attendance_summary_counts_present_and_late_as_attended(entry, registration):
    base = entry.semester.teaching_start
    for offset, status in enumerate(
        [
            AttendanceStatus.PRESENT,
            AttendanceStatus.LATE,
            AttendanceStatus.ABSENT,
            AttendanceStatus.PRESENT,
        ]
    ):
        services.record_session(
            timetable_entry_id=entry.pk,
            session_date=base + timedelta(days=7 * offset),
            marks=[{"registration_id": registration.pk, "status": status}],
            actor=None,
        )
    summary = services.attendance_summary(registration.pk)
    assert summary["sessions_recorded"] == 4
    assert summary["sessions_attended"] == 3
    assert summary["percentage"] == Decimal("75.00")


def test_excused_sessions_do_not_count_against_the_percentage(entry, registration):
    base = entry.semester.teaching_start
    for offset, status in enumerate([AttendanceStatus.ABSENT, AttendanceStatus.EXCUSED]):
        services.record_session(
            timetable_entry_id=entry.pk,
            session_date=base + timedelta(days=7 * offset),
            marks=[{"registration_id": registration.pk, "status": status}],
            actor=None,
        )
    summary = services.attendance_summary(registration.pk)
    # One real session (the absence); the excused one is excluded entirely.
    assert summary["sessions_recorded"] == 1
    assert summary["percentage"] == Decimal("0.00")


def test_a_registration_with_no_records_yet_has_no_percentage(registration):
    summary = services.attendance_summary(registration.pk)
    assert summary["percentage"] is None


def test_below_threshold_flags_a_low_attender(entry, registration, institution):
    institution.attendance_threshold_percent = Decimal("75.00")
    institution.save()
    base = entry.semester.teaching_start
    for offset, status in enumerate(
        [AttendanceStatus.ABSENT, AttendanceStatus.ABSENT, AttendanceStatus.PRESENT]
    ):
        services.record_session(
            timetable_entry_id=entry.pk,
            session_date=base + timedelta(days=7 * offset),
            marks=[{"registration_id": registration.pk, "status": status}],
            actor=None,
        )
    assert services.is_below_threshold(registration.pk) is True


def test_a_registration_with_no_records_is_not_flagged(registration):
    assert services.is_below_threshold(registration.pk) is False


def test_exam_eligibility_blocks_below_threshold_without_a_waiver(entry, registration, institution):
    institution.attendance_threshold_percent = Decimal("75.00")
    institution.save()
    services.record_session(
        timetable_entry_id=entry.pk,
        session_date=entry.semester.teaching_start,
        marks=[{"registration_id": registration.pk, "status": AttendanceStatus.ABSENT}],
        actor=None,
    )
    eligibility = services.exam_eligibility(registration.pk)
    assert eligibility["below_threshold"] is True
    assert eligibility["eligible"] is False


def test_a_granted_waiver_restores_eligibility(entry, registration, institution, registrar):
    institution.attendance_threshold_percent = Decimal("75.00")
    institution.save()
    services.record_session(
        timetable_entry_id=entry.pk,
        session_date=entry.semester.teaching_start,
        marks=[{"registration_id": registration.pk, "status": AttendanceStatus.ABSENT}],
        actor=None,
    )
    services.grant_waiver(registration.pk, actor=registrar, reason="Documented illness")
    eligibility = services.exam_eligibility(registration.pk)
    assert eligibility["waived"] is True
    assert eligibility["eligible"] is True


def test_granting_a_waiver_without_a_reason_is_rejected(registration, registrar):
    with pytest.raises(services.WaiverReasonRequired):
        services.grant_waiver(registration.pk, actor=registrar, reason="   ")
