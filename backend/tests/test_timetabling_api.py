"""
Timetabling API: the registrar builds and publishes; students and lecturers
only ever see the draft/published boundary FR-TT-03 exists to enforce
(FR-TT-01…04).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from apps.timetabling import services
from apps.timetabling.models import DayOfWeek, Room

pytestmark = pytest.mark.django_db

ENTRIES_URL = "/api/v1/timetabling/entries/"
EXAM_ENTRIES_URL = "/api/v1/timetabling/exam-entries/"
ROOMS_URL = "/api/v1/timetabling/rooms/"


@pytest.fixture
def room(db) -> Room:
    return Room.objects.create(code="LR-1", name="Lecture Room 1", capacity=60)


@pytest.fixture
def published_entry(course, semester, room, registrar):
    entry = services.create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.MONDAY,
        start_time="09:00",
        end_time="11:00",
        room_id=room.pk,
        actor=None,
    )
    services.publish_timetable(semester.pk, registrar)
    entry.refresh_from_db()
    return entry


@pytest.fixture
def draft_entry(course, semester, room):
    return services.create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.TUESDAY,
        start_time="09:00",
        end_time="11:00",
        room_id=room.pk,
        actor=None,
    )


@pytest.mark.integration
def test_the_registrar_can_create_and_list_entries(registrar, as_user, course, semester, room):
    response = as_user(registrar).post(
        ENTRIES_URL,
        {
            "course": course.pk,
            "semester": semester.pk,
            "room": room.pk,
            "day_of_week": DayOfWeek.MONDAY,
            "start_time": "09:00",
            "end_time": "11:00",
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["course_code"] == course.code
    assert response.data["is_published"] is False


@pytest.mark.integration
def test_a_room_clash_is_reported_as_a_conflict(
    registrar, as_user, course, semester, room, draft_entry
):
    response = as_user(registrar).post(
        ENTRIES_URL,
        {
            "course": course.pk,
            "semester": semester.pk,
            "room": room.pk,
            "day_of_week": DayOfWeek.TUESDAY,
            "start_time": "10:00",
            "end_time": "12:00",
        },
        format="json",
    )
    assert response.status_code == 409
    assert response.data["error"]["code"] == "room_clash"


@pytest.mark.integration
def test_a_student_only_sees_published_entries(
    student_portal_user, as_user, published_entry, draft_entry
):
    response = as_user(student_portal_user).get(ENTRIES_URL)
    assert response.status_code == 200
    ids = {row["id"] for row in response.data["results"]}
    assert ids == {published_entry.pk}


@pytest.mark.integration
def test_a_student_cannot_create_entries(student_portal_user, as_user, course, semester):
    response = as_user(student_portal_user).post(
        ENTRIES_URL,
        {
            "course": course.pk,
            "semester": semester.pk,
            "day_of_week": DayOfWeek.MONDAY,
            "start_time": "09:00",
            "end_time": "11:00",
        },
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_a_lecturer_sees_their_own_draft_plus_everything_published(
    lecturer, as_user, published_entry, draft_entry, course, semester
):
    own_draft = services.create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.WEDNESDAY,
        start_time="09:00",
        end_time="11:00",
        lecturer_id=lecturer.staff_profile.pk,
        actor=None,
    )
    response = as_user(lecturer).get(ENTRIES_URL)
    assert response.status_code == 200
    ids = {row["id"] for row in response.data["results"]}
    assert ids == {published_entry.pk, own_draft.pk}
    assert draft_entry.pk not in ids


@pytest.mark.integration
def test_the_registrar_can_publish_the_timetable(registrar, as_user, draft_entry, semester):
    response = as_user(registrar).post(
        f"{ENTRIES_URL}publish/", {"semester": semester.pk}, format="json"
    )
    assert response.status_code == 200
    assert response.data["published_count"] == 1
    draft_entry.refresh_from_db()
    assert draft_entry.is_published


@pytest.mark.integration
def test_a_lecturer_cannot_publish_the_timetable(lecturer, as_user, semester):
    response = as_user(lecturer).post(
        f"{ENTRIES_URL}publish/", {"semester": semester.pk}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_the_examinations_office_can_schedule_an_exam(
    examinations_officer, as_user, course, semester, room
):
    exam_date = semester.exam_start + timedelta(days=1)
    response = as_user(examinations_officer).post(
        EXAM_ENTRIES_URL,
        {
            "course": course.pk,
            "semester": semester.pk,
            "room": room.pk,
            "exam_date": str(exam_date),
            "start_time": "09:00",
            "end_time": "12:00",
        },
        format="json",
    )
    assert response.status_code == 201


@pytest.mark.integration
def test_an_exam_outside_the_window_is_a_conflict(
    examinations_officer, as_user, course, semester, room
):
    outside_date = semester.exam_start - timedelta(days=5)
    response = as_user(examinations_officer).post(
        EXAM_ENTRIES_URL,
        {
            "course": course.pk,
            "semester": semester.pk,
            "room": room.pk,
            "exam_date": str(outside_date),
            "start_time": "09:00",
            "end_time": "12:00",
        },
        format="json",
    )
    assert response.status_code == 409
    assert response.data["error"]["code"] == "outside_exam_window"


@pytest.mark.integration
def test_the_registrar_manages_the_room_inventory(registrar, as_user):
    response = as_user(registrar).post(
        ROOMS_URL, {"code": "SCI-1", "name": "Science Lab 1", "capacity": 30}, format="json"
    )
    assert response.status_code == 201


@pytest.mark.integration
def test_a_lecturer_cannot_manage_rooms(lecturer, as_user):
    response = as_user(lecturer).post(
        ROOMS_URL, {"code": "SCI-2", "name": "Science Lab 2", "capacity": 30}, format="json"
    )
    assert response.status_code == 403
