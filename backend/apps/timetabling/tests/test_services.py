"""
Timetabling service layer (FR-TT-01…04): clash detection is the whole point —
publishing and listing are thin wrappers around it.
"""

from __future__ import annotations

from datetime import time, timedelta

import pytest

from apps.timetabling import services
from apps.timetabling.models import DayOfWeek, ExamTimetable, Room, TimetableEntry

pytestmark = pytest.mark.django_db


@pytest.fixture
def room(db) -> Room:
    return Room.objects.create(code="LR-1", name="Lecture Room 1", capacity=60)


@pytest.fixture
def other_room(db) -> Room:
    return Room.objects.create(code="LR-2", name="Lecture Room 2", capacity=40)


@pytest.fixture
def lecturer_profile(lecturer):
    return lecturer.staff_profile


# ------------------------------------------------------------- class timetable


def test_creates_an_entry_with_no_clash(course, semester, room, lecturer_profile):
    entry = services.create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.MONDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        room_id=room.pk,
        lecturer_id=lecturer_profile.pk,
        actor=None,
    )
    assert entry.pk is not None
    assert entry.is_published is False


def test_an_overlapping_room_booking_is_a_clash(course, semester, room):
    services.create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.MONDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        room_id=room.pk,
        actor=None,
    )
    with pytest.raises(services.RoomClash):
        services.create_entry(
            course_id=course.pk,
            semester_id=semester.pk,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(10, 0),
            end_time=time(12, 0),
            room_id=room.pk,
            actor=None,
        )


def test_a_back_to_back_room_booking_is_not_a_clash(course, semester, room):
    services.create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.MONDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        room_id=room.pk,
        actor=None,
    )
    entry = services.create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.MONDAY,
        start_time=time(11, 0),
        end_time=time(13, 0),
        room_id=room.pk,
        actor=None,
    )
    assert entry.pk is not None


def test_the_same_room_on_a_different_day_is_not_a_clash(course, semester, room):
    services.create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.MONDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        room_id=room.pk,
        actor=None,
    )
    entry = services.create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.TUESDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        room_id=room.pk,
        actor=None,
    )
    assert entry.pk is not None


def test_an_overlapping_lecturer_booking_is_a_clash(
    course, semester, room, other_room, lecturer_profile
):
    services.create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.MONDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        room_id=room.pk,
        lecturer_id=lecturer_profile.pk,
        actor=None,
    )
    with pytest.raises(services.LecturerClash):
        services.create_entry(
            course_id=course.pk,
            semester_id=semester.pk,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(10, 30),
            end_time=time(12, 0),
            room_id=other_room.pk,
            lecturer_id=lecturer_profile.pk,
            actor=None,
        )


def test_an_invalid_time_range_is_rejected(course, semester):
    with pytest.raises(services.InvalidTimeRange):
        services.create_entry(
            course_id=course.pk,
            semester_id=semester.pk,
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(11, 0),
            end_time=time(9, 0),
            actor=None,
        )


def test_updating_an_entry_into_a_clash_is_rejected(course, semester, room):
    services.create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.MONDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        room_id=room.pk,
        actor=None,
    )
    movable = services.create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.TUESDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        room_id=room.pk,
        actor=None,
    )
    with pytest.raises(services.RoomClash):
        services.update_entry(movable, day_of_week=DayOfWeek.MONDAY, actor=None)


def test_updating_an_entry_against_itself_is_not_a_clash(course, semester, room):
    entry = services.create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.MONDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        room_id=room.pk,
        actor=None,
    )
    updated = services.update_entry(entry, start_time=time(9, 30), actor=None)
    assert updated.start_time == time(9, 30)


def test_publishing_publishes_every_unpublished_entry_for_the_semester(
    course, semester, room, registrar
):
    services.create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.MONDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        room_id=room.pk,
        actor=None,
    )
    services.create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.TUESDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        room_id=room.pk,
        actor=None,
    )
    count = services.publish_timetable(semester.pk, registrar)
    assert count == 2
    assert all(e.is_published for e in TimetableEntry.objects.filter(semester=semester))


def test_publishing_again_is_a_no_op(course, semester, registrar):
    services.create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.MONDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        actor=None,
    )
    services.publish_timetable(semester.pk, registrar)
    assert services.publish_timetable(semester.pk, registrar) == 0


def test_weekly_timetable_hides_drafts_by_default(course, semester):
    services.create_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        day_of_week=DayOfWeek.MONDAY,
        start_time=time(9, 0),
        end_time=time(11, 0),
        actor=None,
    )
    assert services.weekly_timetable(semester_id=semester.pk) == []
    assert len(services.weekly_timetable(semester_id=semester.pk, published_only=False)) == 1


# -------------------------------------------------------------- exam timetable


def test_creates_an_exam_entry_within_the_exam_window(course, semester, room):
    exam_date = semester.exam_start + timedelta(days=1)
    entry = services.create_exam_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        exam_date=exam_date,
        start_time=time(9, 0),
        end_time=time(12, 0),
        room_id=room.pk,
        actor=None,
    )
    assert entry.pk is not None


def test_an_exam_outside_the_exam_window_is_rejected(course, semester, room):
    outside_date = semester.exam_start - timedelta(days=5)
    with pytest.raises(services.OutsideExamWindow):
        services.create_exam_entry(
            course_id=course.pk,
            semester_id=semester.pk,
            exam_date=outside_date,
            start_time=time(9, 0),
            end_time=time(12, 0),
            room_id=room.pk,
            actor=None,
        )


def test_an_overlapping_exam_room_booking_is_a_clash(course, semester, room, department):
    from apps.curriculum.models import Course

    other_course = Course.objects.create(
        department=department, code="CVE102", title="Statics", credit_hours=3, level=1
    )
    exam_date = semester.exam_start + timedelta(days=1)
    services.create_exam_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        exam_date=exam_date,
        start_time=time(9, 0),
        end_time=time(12, 0),
        room_id=room.pk,
        actor=None,
    )
    with pytest.raises(services.RoomClash):
        services.create_exam_entry(
            course_id=other_course.pk,
            semester_id=semester.pk,
            exam_date=exam_date,
            start_time=time(11, 0),
            end_time=time(13, 0),
            room_id=room.pk,
            actor=None,
        )


def test_an_overlapping_invigilator_assignment_is_a_clash(
    course, semester, room, other_room, department, lecturer_profile
):
    from apps.curriculum.models import Course

    other_course = Course.objects.create(
        department=department, code="CVE103", title="Fluid Mechanics", credit_hours=3, level=2
    )
    exam_date = semester.exam_start + timedelta(days=1)
    services.create_exam_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        exam_date=exam_date,
        start_time=time(9, 0),
        end_time=time(12, 0),
        room_id=room.pk,
        invigilator_ids=[lecturer_profile.pk],
        actor=None,
    )
    with pytest.raises(services.InvigilatorClash):
        services.create_exam_entry(
            course_id=other_course.pk,
            semester_id=semester.pk,
            exam_date=exam_date,
            start_time=time(11, 0),
            end_time=time(13, 0),
            room_id=other_room.pk,
            invigilator_ids=[lecturer_profile.pk],
            actor=None,
        )


def test_publishing_the_exam_timetable(course, semester, room, registrar):
    exam_date = semester.exam_start + timedelta(days=1)
    services.create_exam_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        exam_date=exam_date,
        start_time=time(9, 0),
        end_time=time(12, 0),
        room_id=room.pk,
        actor=None,
    )
    count = services.publish_exam_timetable(semester.pk, registrar)
    assert count == 1
    assert ExamTimetable.objects.get(course=course, semester=semester).is_published


def test_exam_schedule_hides_drafts_by_default(course, semester, room):
    exam_date = semester.exam_start + timedelta(days=1)
    services.create_exam_entry(
        course_id=course.pk,
        semester_id=semester.pk,
        exam_date=exam_date,
        start_time=time(9, 0),
        end_time=time(12, 0),
        room_id=room.pk,
        actor=None,
    )
    assert services.exam_schedule(semester_id=semester.pk) == []
    assert len(services.exam_schedule(semester_id=semester.pk, published_only=False)) == 1
