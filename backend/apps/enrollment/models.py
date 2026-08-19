"""
Course registration (FR-ENR-01…05).

One row per (student, course, semester) — a retake in a later semester is a new
row, which is what makes `is_repeat` a plain "have I ever registered for this
course before" query rather than something that needs semester ordering logic.

Prerequisite checking (FR-ENR-02) reads "passed" from this model's own
`COMPLETED` registrations. Nothing marks a registration `COMPLETED` yet — that
becomes real once Phase 3 publishes results. Until then, `record_prior_completion`
exists as the deliberately narrow, registrar-authorised stand-in for transfer
credit and legacy records (FR-REG-05), and it is what lets a prerequisite chain
be demonstrated end to end before Phase 3 lands.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditedModel
from apps.core.models import TimeStampedModel

__all__ = ["CourseRegistration", "RegistrationStatus"]


class RegistrationStatus(models.TextChoices):
    REGISTERED = "registered", _("Registered")
    DROPPED = "dropped", _("Dropped")
    COMPLETED = "completed", _("Completed")


class CourseRegistration(AuditedModel, TimeStampedModel):
    audit_fields = ("status", "is_repeat")

    student = models.ForeignKey(
        "registry.Student", on_delete=models.PROTECT, related_name="course_registrations"
    )
    course = models.ForeignKey(
        "curriculum.Course", on_delete=models.PROTECT, related_name="registrations"
    )
    semester = models.ForeignKey(
        "academics.Semester", on_delete=models.PROTECT, related_name="course_registrations"
    )

    status = models.CharField(
        _("status"),
        max_length=15,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.REGISTERED,
    )
    is_repeat = models.BooleanField(
        _("repeat/carry-over"),
        default=False,
        help_text=_(
            "Set automatically: the student has registered for this course before (FR-ENR-05)."
        ),
    )

    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    dropped_at = models.DateTimeField(null=True, blank=True)
    drop_reason = models.TextField(blank=True)

    hold_override_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=_("Set when a registrar registered this student despite a blocking hold."),
    )
    override_reason = models.TextField(blank=True)

    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("course registration")
        verbose_name_plural = _("course registrations")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "course", "semester"],
                name="one_registration_per_course_per_semester",
            ),
        ]
        indexes = [
            models.Index(fields=["course", "semester", "status"]),
            models.Index(fields=["student", "status"]),
        ]
        permissions = [
            ("override_hold", _("Can register a student despite a blocking hold")),
            # Distinct from change_courseregistration: a student holds that
            # permission too, scoped to their own rows, so it cannot be what
            # gates recording transfer credit / legacy completions.
            ("record_completion", _("Can record a course registration as completed")),
        ]

    def __str__(self) -> str:
        return f"{self.student_id} → {self.course_id} ({self.semester_id}) [{self.status}]"
