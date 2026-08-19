"""
Attendance (FR-ATT-01…02).

`SessionRecord` keys off the *registration*, not the student: a repeat's
attendance must never be conflated with the original attempt's, the same
distinction `enrollment.CourseRegistration.is_repeat` exists to draw. The
percentage a threshold check reads is therefore always scoped to one attempt
at one course in one semester.

A lecturer taking a register is expected to mark every enrolled student
present, absent, late or excused in one sitting — `attendance_summary` reads
"how many sessions has this registration got a row for at all" as the
denominator, not "how many sessions did the timetable schedule", because a
class that met but was never recorded is invisible to this system by
definition, the same way an ungraded course is invisible until someone enters
a mark.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditedModel
from apps.core.models import TimeStampedModel

__all__ = ["AttendanceStatus", "AttendanceWaiver", "SessionRecord"]


class AttendanceStatus(models.TextChoices):
    PRESENT = "present", _("Present")
    ABSENT = "absent", _("Absent")
    LATE = "late", _("Late")
    EXCUSED = "excused", _("Excused")


class SessionRecord(AuditedModel, TimeStampedModel):
    """One student's attendance mark for one dated occurrence of a class."""

    audit_fields = ("status",)
    audit_sensitive = True

    timetable_entry = models.ForeignKey(
        "timetabling.TimetableEntry", on_delete=models.PROTECT, related_name="session_records"
    )
    registration = models.ForeignKey(
        "enrollment.CourseRegistration", on_delete=models.PROTECT, related_name="session_records"
    )
    session_date = models.DateField(_("session date"))
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.PRESENT,
    )
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = _("session record")
        verbose_name_plural = _("session records")
        ordering = ["-session_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["timetable_entry", "session_date", "registration"],
                name="one_record_per_student_per_session",
            ),
        ]
        indexes = [
            models.Index(fields=["registration", "session_date"]),
            models.Index(fields=["timetable_entry", "session_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.registration_id} · {self.session_date} · {self.status}"


class AttendanceWaiver(AuditedModel, TimeStampedModel):
    """An authorised exception to the exam block a low attendance percentage
    would otherwise trigger (FR-ATT-02). One per registration: granting a
    second waiver replaces the reason on record rather than stacking silently."""

    audit_fields = ("reason",)
    audit_sensitive = True

    registration = models.OneToOneField(
        "enrollment.CourseRegistration", on_delete=models.CASCADE, related_name="attendance_waiver"
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reason = models.TextField(_("reason"))

    class Meta:
        verbose_name = _("attendance waiver")
        verbose_name_plural = _("attendance waivers")
        permissions = [
            (
                "override_block",
                _(
                    "Can authorise a registration to sit an exam despite a low attendance percentage"
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"Waiver for registration {self.registration_id}"
