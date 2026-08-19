"""
Attendance API: a lecturer records their own class's register; a student sees
only their own attendance; the examinations office alone may waive a block
(FR-ATT-01…02).
"""

from __future__ import annotations

from datetime import time

import pytest

from apps.attendance.models import AttendanceStatus
from apps.enrollment.services import register_course
from apps.timetabling.models import DayOfWeek
from apps.timetabling.services import create_entry

pytestmark = pytest.mark.django_db

RECORDS_URL = "/api/v1/attendance/records/"


@pytest.fixture
def entry(course, semester, lecturer):
    return create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.MONDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        lecturer_id=lecturer.staff_profile.pk,
        actor=None,
    )


@pytest.fixture
def registration(student_portal_user, student, course, semester, registrar):
    return register_course(
        student_id=student.pk, course_id=course.pk, semester_id=semester.pk, actor=registrar
    )


@pytest.mark.integration
def test_a_lecturer_can_record_their_own_class(lecturer, as_user, entry, registration, semester):
    response = as_user(lecturer).post(
        f"{RECORDS_URL}record/",
        {
            "timetable_entry": entry.pk,
            "session_date": str(semester.teaching_start),
            "marks": [{"registration_id": registration.pk, "status": AttendanceStatus.PRESENT}],
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.data[0]["status"] == AttendanceStatus.PRESENT


@pytest.mark.integration
def test_a_student_cannot_record_attendance(
    student_portal_user, as_user, entry, registration, semester
):
    response = as_user(student_portal_user).post(
        f"{RECORDS_URL}record/",
        {
            "timetable_entry": entry.pk,
            "session_date": str(semester.teaching_start),
            "marks": [{"registration_id": registration.pk, "status": AttendanceStatus.PRESENT}],
        },
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_marking_an_unregistered_student_is_a_conflict(lecturer, as_user, entry, semester):
    response = as_user(lecturer).post(
        f"{RECORDS_URL}record/",
        {
            "timetable_entry": entry.pk,
            "session_date": str(semester.teaching_start),
            "marks": [{"registration_id": 999999, "status": AttendanceStatus.PRESENT}],
        },
        format="json",
    )
    assert response.status_code == 400
    assert response.data["error"]["code"] == "unregistered_student"


@pytest.mark.integration
def test_a_student_sees_only_their_own_records(
    lecturer, as_user, student_portal_user, entry, registration, semester
):
    as_user(lecturer).post(
        f"{RECORDS_URL}record/",
        {
            "timetable_entry": entry.pk,
            "session_date": str(semester.teaching_start),
            "marks": [{"registration_id": registration.pk, "status": AttendanceStatus.PRESENT}],
        },
        format="json",
    )
    response = as_user(student_portal_user).get(RECORDS_URL)
    assert response.status_code == 200
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["registration"] == registration.pk


@pytest.mark.integration
def test_a_student_can_see_their_own_summary(
    lecturer, as_user, student_portal_user, entry, registration, semester
):
    as_user(lecturer).post(
        f"{RECORDS_URL}record/",
        {
            "timetable_entry": entry.pk,
            "session_date": str(semester.teaching_start),
            "marks": [{"registration_id": registration.pk, "status": AttendanceStatus.PRESENT}],
        },
        format="json",
    )
    response = as_user(student_portal_user).get(
        f"/api/v1/attendance/registrations/{registration.pk}/summary/"
    )
    assert response.status_code == 200
    assert response.data["sessions_recorded"] == 1


@pytest.mark.integration
def test_a_lecturer_cannot_view_someone_elses_summary(lecturer, as_user, registration):
    response = as_user(lecturer).get(f"/api/v1/attendance/registrations/{registration.pk}/summary/")
    assert response.status_code == 403


@pytest.mark.integration
def test_the_examinations_office_can_view_eligibility(examinations_officer, as_user, registration):
    response = as_user(examinations_officer).get(
        f"/api/v1/attendance/registrations/{registration.pk}/eligibility/"
    )
    assert response.status_code == 200
    assert response.data["eligible"] is True


@pytest.mark.integration
def test_only_the_examinations_office_may_grant_a_waiver(registrar, as_user, registration):
    response = as_user(registrar).post(
        f"/api/v1/attendance/registrations/{registration.pk}/waive/",
        {"reason": "Approved by the dean"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_the_examinations_office_can_grant_a_waiver(examinations_officer, as_user, registration):
    response = as_user(examinations_officer).post(
        f"/api/v1/attendance/registrations/{registration.pk}/waive/",
        {"reason": "Approved by the dean"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["waived"] is True


@pytest.mark.integration
def test_a_waiver_without_a_reason_is_rejected(examinations_officer, as_user, registration):
    response = as_user(examinations_officer).post(
        f"/api/v1/attendance/registrations/{registration.pk}/waive/", {"reason": ""}, format="json"
    )
    assert response.status_code == 400
