"""
Examinations and results (FR-EXM-01…08).

`Mark` keys off the *registration*, not the student — the same reason
`attendance.SessionRecord` does: a repeat's marks must never be conflated
with the original attempt's.

Assessment weights are not validated to sum to 100 on save: a lecturer builds
a scheme up one component at a time ("CA1: 20%", then "CA2: 20%", then
"Final: 60%"), and rejecting the first two because they do not yet total 100
would make the scheme impossible to build incrementally. The sum is instead
validated in `services.course_result`, at the point a percentage is actually
computed from it — the same "validate where it is used" choice
`academics.services.grading.grade_for` makes for a grading scale with a gap.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditedModel
from apps.core.models import TimeStampedModel

__all__ = [
    "AppealStatus",
    "ApprovalStatus",
    "Assessment",
    "GradeAppeal",
    "Mark",
    "ResultApproval",
]


class Assessment(AuditedModel, TimeStampedModel):
    """One graded component of a course — a CA test, a project, the final
    exam — and the weight it carries toward the course result (FR-EXM-01)."""

    audit_fields = ("name", "weight_percent", "max_score", "grade_entry_deadline")

    course = models.ForeignKey(
        "curriculum.Course", on_delete=models.PROTECT, related_name="assessments"
    )
    name = models.CharField(_("name"), max_length=100)
    weight_percent = models.DecimalField(
        _("weight %"),
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    max_score = models.DecimalField(
        _("maximum score"), max_digits=6, decimal_places=2, default=Decimal("100")
    )
    sequence = models.PositiveSmallIntegerField(_("sequence"), default=1)
    grade_entry_deadline = models.DateTimeField(_("grade entry deadline"), null=True, blank=True)

    class Meta:
        verbose_name = _("assessment")
        verbose_name_plural = _("assessments")
        ordering = ["course", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["course", "name"], name="one_assessment_name_per_course"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.course_id} · {self.name} ({self.weight_percent}%)"


class Mark(AuditedModel, TimeStampedModel):
    """One student's score for one assessment component, against the
    registration it belongs to (FR-EXM-01, FR-EXM-02, FR-EXM-08)."""

    audit_fields = ("score", "moderated_score", "is_irregular")
    audit_sensitive = True

    registration = models.ForeignKey(
        "enrollment.CourseRegistration", on_delete=models.PROTECT, related_name="marks"
    )
    assessment = models.ForeignKey(Assessment, on_delete=models.PROTECT, related_name="marks")
    score = models.DecimalField(_("score"), max_digits=6, decimal_places=2)
    is_late = models.BooleanField(
        _("entered late"),
        default=False,
        help_text=_("Set automatically against the assessment's grade entry deadline (FR-EXM-02)."),
    )

    moderated_score = models.DecimalField(
        _("moderated score"), max_digits=6, decimal_places=2, null=True, blank=True
    )
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    moderation_notes = models.TextField(_("moderation notes"), blank=True)

    is_irregular = models.BooleanField(
        _("flagged irregular"),
        default=False,
        help_text=_(
            "Exam malpractice or another irregularity (FR-EXM-08). Excludes this mark "
            "from a course result until cleared."
        ),
    )
    irregularity_notes = models.TextField(_("irregularity notes"), blank=True)

    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = _("mark")
        verbose_name_plural = _("marks")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["registration", "assessment"],
                name="one_mark_per_registration_per_assessment",
            ),
        ]
        indexes = [
            models.Index(fields=["registration"]),
            models.Index(fields=["assessment"]),
        ]
        permissions = [
            ("moderate_result", "Can moderate (second-mark) a mark"),
            ("flag_irregularity", "Can flag or clear an exam irregularity on a mark"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.assessment_id and self.score is not None and self.score > self.assessment.max_score:
            raise ValidationError(
                {
                    "score": _("The score cannot exceed the assessment's maximum of %(max)s.")
                    % {"max": self.assessment.max_score}
                }
            )
        if self.score is not None and self.score < 0:
            raise ValidationError({"score": _("The score cannot be negative.")})

    @property
    def effective_score(self) -> Decimal:
        return self.moderated_score if self.moderated_score is not None else self.score

    def __str__(self) -> str:
        return f"{self.registration_id} · {self.assessment_id} = {self.effective_score}"


class AppealStatus(models.TextChoices):
    SUBMITTED = "submitted", _("Submitted")
    UNDER_REVIEW = "under_review", _("Under review")
    UPHELD = "upheld", _("Upheld")
    REJECTED = "rejected", _("Rejected")


class GradeAppeal(AuditedModel, TimeStampedModel):
    """A student's challenge to a mark, or to a course result as a whole
    (FR-EXM-07). `assessment` left blank means the appeal is about the overall
    result rather than one component."""

    audit_fields = ("status",)
    audit_sensitive = True

    registration = models.ForeignKey(
        "enrollment.CourseRegistration", on_delete=models.PROTECT, related_name="grade_appeals"
    )
    assessment = models.ForeignKey(
        Assessment, on_delete=models.PROTECT, null=True, blank=True, related_name="appeals"
    )
    reason = models.TextField(_("reason"))
    status = models.CharField(
        _("status"), max_length=15, choices=AppealStatus.choices, default=AppealStatus.SUBMITTED
    )

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    decision_notes = models.TextField(_("decision notes"), blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("grade appeal")
        verbose_name_plural = _("grade appeals")
        ordering = ["-created_at"]
        permissions = [
            ("decide_gradeappeal", _("Can decide a grade appeal")),
        ]

    def __str__(self) -> str:
        return f"Appeal on registration {self.registration_id} [{self.status}]"


class ApprovalStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    APPROVED = "approved", _("Approved")
    REJECTED = "rejected", _("Rejected")
    PUBLISHED = "published", _("Published")


class ResultApproval(AuditedModel, TimeStampedModel):
    """Senate/exam board sign-off before a semester's results reach students
    (FR-EXM-05). `programme` left blank covers every programme in the
    semester at once; scoping one row per programme lets a faculty publish
    early without waiting on another that is still moderating."""

    audit_fields = ("status",)
    audit_sensitive = True

    semester = models.ForeignKey(
        "academics.Semester", on_delete=models.PROTECT, related_name="result_approvals"
    )
    programme = models.ForeignKey(
        "curriculum.Programme",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="result_approvals",
    )
    status = models.CharField(
        _("status"), max_length=15, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_notes = models.TextField(_("approval notes"), blank=True)

    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("result approval")
        verbose_name_plural = _("result approvals")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["semester", "programme"],
                condition=models.Q(programme__isnull=False),
                name="one_approval_per_semester_per_programme",
            ),
            models.UniqueConstraint(
                fields=["semester"],
                condition=models.Q(programme__isnull=True),
                name="one_all_programme_approval_per_semester",
            ),
        ]
        permissions = [
            ("approve_result", "Can approve a semester's results for publication (Senate)"),
            ("publish_result", "Can publish approved results to students"),
        ]

    def __str__(self) -> str:
        scope = self.programme_id or "all programmes"
        return f"{self.semester_id} · {scope} [{self.status}]"
