"""
Timetabling: the weekly class schedule (FR-TT-01…03) and the exam schedule
(FR-TT-04).

Clash detection is scoped to what today's data can prove without ambiguity: a
room is one physical place and a lecturer is one person, so double-booking
either is always a real clash. Detecting a clash for the *students* who would
have to be in two places at once needs a class-group/section model this system
does not have — automated timetable generation stays a stretch goal (D-3) and
this deferral is recorded as D-7 in `docs/TRACEABILITY.md`; a registrar builds
the timetable by hand, protected from the clashes today's data can prove.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditedModel
from apps.core.models import TimeStampedModel

__all__ = ["DayOfWeek", "ExamTimetable", "Room", "TimetableEntry"]


class DayOfWeek(models.IntegerChoices):
    MONDAY = 0, _("Monday")
    TUESDAY = 1, _("Tuesday")
    WEDNESDAY = 2, _("Wednesday")
    THURSDAY = 3, _("Thursday")
    FRIDAY = 4, _("Friday")
    SATURDAY = 5, _("Saturday")
    SUNDAY = 6, _("Sunday")


class Room(AuditedModel, TimeStampedModel):
    audit_fields = ("code", "name", "capacity", "is_active")

    code = models.CharField(_("code"), max_length=20, unique=True)
    name = models.CharField(_("name"), max_length=150)
    building = models.CharField(_("building"), max_length=100, blank=True)
    capacity = models.PositiveIntegerField(_("capacity"), default=0)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class TimetableEntry(AuditedModel, TimeStampedModel):
    """One recurring weekly class slot for a course, in a semester."""

    audit_fields = (
        "course",
        "semester",
        "day_of_week",
        "start_time",
        "end_time",
        "room",
        "lecturer",
        "is_published",
    )

    course = models.ForeignKey(
        "curriculum.Course", on_delete=models.PROTECT, related_name="timetable_entries"
    )
    semester = models.ForeignKey(
        "academics.Semester", on_delete=models.PROTECT, related_name="timetable_entries"
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="timetable_entries",
    )
    lecturer = models.ForeignKey(
        "registry.StaffProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="timetable_entries",
    )

    day_of_week = models.PositiveSmallIntegerField(_("day of week"), choices=DayOfWeek.choices)
    start_time = models.TimeField(_("starts"))
    end_time = models.TimeField(_("ends"))

    is_published = models.BooleanField(_("published"), default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = _("timetable entry")
        verbose_name_plural = _("timetable entries")
        ordering = ["day_of_week", "start_time"]
        indexes = [
            models.Index(fields=["semester", "day_of_week"]),
            models.Index(fields=["room", "semester", "day_of_week"]),
            models.Index(fields=["lecturer", "semester", "day_of_week"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.course_id} · {self.get_day_of_week_display()} {self.start_time}–{self.end_time}"
        )


class ExamTimetable(AuditedModel, TimeStampedModel):
    """One scheduled exam sitting for a course, in a semester (FR-TT-04).

    `invigilators` is deliberately outside `audit_fields`: `AuditedModel`
    diffs plain columns read from the instance's own attributes, and a
    many-to-many is neither — it lives in a through table and is never part of
    what `save()` writes. Assigning it always goes through `.set()` after the
    row exists.
    """

    audit_fields = (
        "course",
        "semester",
        "exam_date",
        "start_time",
        "end_time",
        "room",
        "is_published",
    )

    course = models.ForeignKey(
        "curriculum.Course", on_delete=models.PROTECT, related_name="exam_timetable_entries"
    )
    semester = models.ForeignKey(
        "academics.Semester", on_delete=models.PROTECT, related_name="exam_timetable_entries"
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="exam_timetable_entries",
    )
    invigilators = models.ManyToManyField(
        "registry.StaffProfile", blank=True, related_name="invigilating_exams"
    )

    exam_date = models.DateField(_("exam date"))
    start_time = models.TimeField(_("starts"))
    end_time = models.TimeField(_("ends"))

    is_published = models.BooleanField(_("published"), default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = _("exam timetable entry")
        verbose_name_plural = _("exam timetable entries")
        ordering = ["exam_date", "start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["course", "semester"], name="one_exam_sitting_per_course_per_semester"
            ),
        ]
        indexes = [
            models.Index(fields=["semester", "exam_date"]),
            models.Index(fields=["room", "exam_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.course_id} exam · {self.exam_date}"
