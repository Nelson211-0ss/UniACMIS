"""
Timetabling services (FR-TT-01…04).

Two independent schedules share this module: the recurring weekly class
timetable, and the date-specific exam timetable. Each publishes separately —
publishing the class timetable says nothing about whether the exam timetable
is ready, and vice versa.
"""

from __future__ import annotations

from datetime import date, time
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.timetabling.models import ExamTimetable, Room, TimetableEntry


class RoomClash(DomainError):
    code = "room_clash"
    message = "This room is already booked for an overlapping time."
    status_code = 409


class LecturerClash(DomainError):
    code = "lecturer_clash"
    message = "This lecturer is already scheduled for an overlapping time."
    status_code = 409


class InvigilatorClash(DomainError):
    code = "invigilator_clash"
    message = "One of these invigilators is already assigned to another exam at this time."
    status_code = 409


class InvalidTimeRange(DomainError):
    code = "invalid_time_range"
    message = "The start time must be before the end time."


class OutsideExamWindow(DomainError):
    code = "outside_exam_window"
    message = "This exam date falls outside the semester's examination period."
    status_code = 409


def _overlap(start_a: time, end_a: time, start_b: time, end_b: time) -> bool:
    return start_a < end_b and start_b < end_a


# ------------------------------------------------------------------------ rooms


def create_room(
    *, code: str, name: str, building: str = "", capacity: int = 0, actor: Any = None
) -> Room:
    room = Room(code=code, name=name, building=building, capacity=capacity)
    room.audit_reason = "Room created"
    room.full_clean()
    room.save()
    return room


def update_room(
    room: Room,
    *,
    name: str | None = None,
    building: str | None = None,
    capacity: int | None = None,
    is_active: bool | None = None,
    actor: Any = None,
) -> Room:
    if name is not None:
        room.name = name
    if building is not None:
        room.building = building
    if capacity is not None:
        room.capacity = capacity
    if is_active is not None:
        room.is_active = is_active
    room.audit_reason = "Room updated"
    room.full_clean()
    room.save()
    return room


# ------------------------------------------------------------- class timetable


def _room_busy(
    room_id: int | None,
    semester_id: int,
    day_of_week: int,
    start_time: time,
    end_time: time,
    exclude_pk: int | None = None,
) -> bool:
    if room_id is None:
        return False
    queryset = TimetableEntry.objects.filter(
        room_id=room_id, semester_id=semester_id, day_of_week=day_of_week
    )
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    return any(_overlap(start_time, end_time, e.start_time, e.end_time) for e in queryset)


def _lecturer_busy(
    lecturer_id: int | None,
    semester_id: int,
    day_of_week: int,
    start_time: time,
    end_time: time,
    exclude_pk: int | None = None,
) -> bool:
    if lecturer_id is None:
        return False
    queryset = TimetableEntry.objects.filter(
        lecturer_id=lecturer_id, semester_id=semester_id, day_of_week=day_of_week
    )
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    return any(_overlap(start_time, end_time, e.start_time, e.end_time) for e in queryset)


@transaction.atomic
def create_entry(
    *,
    course_id: int,
    semester_id: int,
    day_of_week: int,
    start_time: time,
    end_time: time,
    room_id: int | None = None,
    lecturer_id: int | None = None,
    actor: Any = None,
) -> TimetableEntry:
    if start_time >= end_time:
        raise InvalidTimeRange()
    if _room_busy(room_id, semester_id, day_of_week, start_time, end_time):
        raise RoomClash()
    if _lecturer_busy(lecturer_id, semester_id, day_of_week, start_time, end_time):
        raise LecturerClash()

    entry = TimetableEntry(
        course_id=course_id,
        semester_id=semester_id,
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        room_id=room_id,
        lecturer_id=lecturer_id,
    )
    entry.audit_reason = "Timetable entry created"
    entry.full_clean()
    entry.save()
    return entry


@transaction.atomic
def update_entry(
    entry: TimetableEntry,
    *,
    day_of_week: int | None = None,
    start_time: time | None = None,
    end_time: time | None = None,
    room_id: int | Any | None = "__unset__",
    lecturer_id: int | Any | None = "__unset__",
    actor: Any = None,
) -> TimetableEntry:
    new_day = entry.day_of_week if day_of_week is None else day_of_week
    new_start = entry.start_time if start_time is None else start_time
    new_end = entry.end_time if end_time is None else end_time
    new_room = entry.room_id if room_id == "__unset__" else room_id
    new_lecturer = entry.lecturer_id if lecturer_id == "__unset__" else lecturer_id

    if new_start >= new_end:
        raise InvalidTimeRange()
    if _room_busy(new_room, entry.semester_id, new_day, new_start, new_end, exclude_pk=entry.pk):
        raise RoomClash()
    if _lecturer_busy(
        new_lecturer, entry.semester_id, new_day, new_start, new_end, exclude_pk=entry.pk
    ):
        raise LecturerClash()

    entry.day_of_week = new_day
    entry.start_time = new_start
    entry.end_time = new_end
    entry.room_id = new_room
    entry.lecturer_id = new_lecturer
    entry.audit_reason = "Timetable entry updated"
    entry.full_clean()
    entry.save()
    return entry


def publish_timetable(semester_id: int, actor: Any) -> int:
    """FR-TT-03. Publishes every unpublished entry for the semester at once —
    a partially published class timetable is worse than none, since it looks
    complete on the notice board."""
    now = timezone.now()
    entries = list(TimetableEntry.objects.filter(semester_id=semester_id, is_published=False))
    for entry in entries:
        entry.is_published = True
        entry.published_at = now
        entry.published_by = actor if getattr(actor, "pk", None) else None
        entry.audit_reason = "Timetable published"
        entry.save()
    return len(entries)


def entry_context(timetable_entry_id: int) -> tuple[int, int]:
    """(course_id, semester_id) for a class slot — what `attendance` needs to
    validate a session against the right course's roster, without importing
    `TimetableEntry` itself."""
    course_id, semester_id = TimetableEntry.objects.values_list("course_id", "semester_id").get(
        pk=timetable_entry_id
    )
    return course_id, semester_id


def weekly_timetable(
    *,
    semester_id: int,
    course_id: int | None = None,
    lecturer_id: int | None = None,
    room_id: int | None = None,
    published_only: bool = True,
) -> list[TimetableEntry]:
    """FR-TT-03. The notice-board and portal view: everyone who can see a
    published class timetable sees the same rows, filtered by course, teacher
    or room — never by student, since a lecture is not private to who is
    registered for it."""
    queryset = TimetableEntry.objects.filter(semester_id=semester_id).select_related(
        "course", "room", "lecturer__user"
    )
    if published_only:
        queryset = queryset.filter(is_published=True)
    if course_id is not None:
        queryset = queryset.filter(course_id=course_id)
    if lecturer_id is not None:
        queryset = queryset.filter(lecturer_id=lecturer_id)
    if room_id is not None:
        queryset = queryset.filter(room_id=room_id)
    return list(queryset.order_by("day_of_week", "start_time"))


# -------------------------------------------------------------- exam timetable


def _exam_room_busy(
    room_id: int | None,
    exam_date: date,
    start_time: time,
    end_time: time,
    exclude_pk: int | None = None,
) -> bool:
    if room_id is None:
        return False
    queryset = ExamTimetable.objects.filter(room_id=room_id, exam_date=exam_date)
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    return any(_overlap(start_time, end_time, e.start_time, e.end_time) for e in queryset)


def _invigilators_busy(
    invigilator_ids: list[int],
    exam_date: date,
    start_time: time,
    end_time: time,
    exclude_pk: int | None = None,
) -> bool:
    if not invigilator_ids:
        return False
    queryset = ExamTimetable.objects.filter(
        exam_date=exam_date, invigilators__id__in=invigilator_ids
    ).distinct()
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    return any(_overlap(start_time, end_time, e.start_time, e.end_time) for e in queryset)


@transaction.atomic
def create_exam_entry(
    *,
    course_id: int,
    semester_id: int,
    exam_date: date,
    start_time: time,
    end_time: time,
    room_id: int | None = None,
    invigilator_ids: list[int] | None = None,
    actor: Any = None,
) -> ExamTimetable:
    from apps.academics.services import calendar

    semester = calendar.get_semester(semester_id)
    if start_time >= end_time:
        raise InvalidTimeRange()
    if (
        semester.exam_start
        and semester.exam_end
        and not (semester.exam_start <= exam_date <= semester.exam_end)
    ):
        raise OutsideExamWindow()

    invigilator_ids = invigilator_ids or []
    if _exam_room_busy(room_id, exam_date, start_time, end_time):
        raise RoomClash()
    if _invigilators_busy(invigilator_ids, exam_date, start_time, end_time):
        raise InvigilatorClash()

    entry = ExamTimetable(
        course_id=course_id,
        semester_id=semester_id,
        exam_date=exam_date,
        start_time=start_time,
        end_time=end_time,
        room_id=room_id,
    )
    entry.audit_reason = "Exam scheduled"
    entry.full_clean()
    entry.save()
    if invigilator_ids:
        entry.invigilators.set(invigilator_ids)
    return entry


@transaction.atomic
def update_exam_entry(
    entry: ExamTimetable,
    *,
    exam_date: date | None = None,
    start_time: time | None = None,
    end_time: time | None = None,
    room_id: int | Any | None = "__unset__",
    invigilator_ids: list[int] | None = None,
    actor: Any = None,
) -> ExamTimetable:
    from apps.academics.services import calendar

    new_date = entry.exam_date if exam_date is None else exam_date
    new_start = entry.start_time if start_time is None else start_time
    new_end = entry.end_time if end_time is None else end_time
    new_room = entry.room_id if room_id == "__unset__" else room_id

    semester = calendar.get_semester(entry.semester_id)
    if new_start >= new_end:
        raise InvalidTimeRange()
    if (
        semester.exam_start
        and semester.exam_end
        and not (semester.exam_start <= new_date <= semester.exam_end)
    ):
        raise OutsideExamWindow()

    if _exam_room_busy(new_room, new_date, new_start, new_end, exclude_pk=entry.pk):
        raise RoomClash()
    if invigilator_ids is not None and _invigilators_busy(
        invigilator_ids, new_date, new_start, new_end, exclude_pk=entry.pk
    ):
        raise InvigilatorClash()

    entry.exam_date = new_date
    entry.start_time = new_start
    entry.end_time = new_end
    entry.room_id = new_room
    entry.audit_reason = "Exam schedule updated"
    entry.full_clean()
    entry.save()
    if invigilator_ids is not None:
        entry.invigilators.set(invigilator_ids)
    return entry


def publish_exam_timetable(semester_id: int, actor: Any) -> int:
    now = timezone.now()
    entries = list(ExamTimetable.objects.filter(semester_id=semester_id, is_published=False))
    for entry in entries:
        entry.is_published = True
        entry.published_at = now
        entry.published_by = actor if getattr(actor, "pk", None) else None
        entry.audit_reason = "Exam timetable published"
        entry.save()
    return len(entries)


def exam_schedule(
    *, semester_id: int, course_id: int | None = None, published_only: bool = True
) -> list[ExamTimetable]:
    queryset = (
        ExamTimetable.objects.filter(semester_id=semester_id)
        .select_related("course", "room")
        .prefetch_related("invigilators__user")
    )
    if published_only:
        queryset = queryset.filter(is_published=True)
    if course_id is not None:
        queryset = queryset.filter(course_id=course_id)
    return list(queryset.order_by("exam_date", "start_time"))


def exam_entry_for(course_id: int, semester_id: int) -> ExamTimetable | None:
    """Used by `examinations` to find when/where a course's exam sits, e.g. to
    report a mark entered before the sitting even happened."""
    return (
        ExamTimetable.objects.filter(course_id=course_id, semester_id=semester_id)
        .select_related("room")
        .first()
    )
