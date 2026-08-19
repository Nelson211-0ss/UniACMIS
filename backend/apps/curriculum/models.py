"""
Academic structure: Faculty → Department → Programme → Course (FR-CUR-01).

Two decisions shape this module:

**Courses are owned by a department and referenced by curricula.** A service
course taught to five programmes exists once, so a change to its credit hours
cannot silently disagree between them.

**Curricula are versioned** (FR-CUR-03). A student is bound to the version they
entered under. Without that, editing a programme's course list in 2029 would
retroactively change what the 2026 cohort was required to pass, which makes their
transcripts indefensible.

Nothing here is hard-deleted. A transcript issued in 2040 still refers to the
programme and courses as they were.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditedModel
from apps.core.models import SoftDeleteModel, TimeStampedModel


class Faculty(AuditedModel, TimeStampedModel, SoftDeleteModel):
    audit_fields = ("name", "code", "is_active", "deleted_at")

    institution = models.ForeignKey(
        "academics.Institution", on_delete=models.CASCADE, related_name="faculties"
    )
    name = models.CharField(_("name"), max_length=200)
    code = models.CharField(
        _("code"),
        max_length=10,
        unique=True,
        help_text=_("Short code used in student IDs, e.g. ENG."),
    )
    description = models.TextField(_("description"), blank=True)
    dean = models.ForeignKey(
        "registry.StaffProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deanships",
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("faculty")
        verbose_name_plural = _("faculties")
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        return super().save(*args, **kwargs)


class Department(AuditedModel, TimeStampedModel, SoftDeleteModel):
    audit_fields = ("name", "code", "head", "is_active", "deleted_at")

    faculty = models.ForeignKey(Faculty, on_delete=models.PROTECT, related_name="departments")
    name = models.CharField(_("name"), max_length=200)
    code = models.CharField(_("code"), max_length=10, unique=True)
    description = models.TextField(_("description"), blank=True)
    head = models.ForeignKey(
        "registry.StaffProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="headships",
        help_text=_("Defines the scope of the Head of Department role."),
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("department")
        verbose_name_plural = _("departments")
        ordering = ["faculty__name", "name"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        return super().save(*args, **kwargs)


class Award(models.TextChoices):
    CERTIFICATE = "certificate", _("Certificate")
    DIPLOMA = "diploma", _("Diploma")
    BACHELOR = "bachelor", _("Bachelor's Degree")
    POSTGRAD_DIPLOMA = "postgraduate_diploma", _("Postgraduate Diploma")
    MASTERS = "masters", _("Master's Degree")
    PHD = "phd", _("Doctorate")


class Programme(AuditedModel, TimeStampedModel, SoftDeleteModel):
    audit_fields = (
        "name",
        "code",
        "award",
        "duration_years",
        "total_credits_required",
        "max_credits_per_semester",
        "is_active",
        "deleted_at",
    )

    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="programmes")
    name = models.CharField(_("name"), max_length=200)
    code = models.CharField(
        _("code"), max_length=15, unique=True, help_text=_("Used in student IDs, e.g. CIV.")
    )
    award = models.CharField(_("award"), max_length=25, choices=Award.choices)
    duration_years = models.PositiveSmallIntegerField(
        _("duration (years)"), validators=[MinValueValidator(1), MaxValueValidator(10)]
    )

    total_credits_required = models.PositiveSmallIntegerField(
        _("credits required to graduate"), default=120
    )
    min_credits_per_semester = models.PositiveSmallIntegerField(
        _("minimum credits per semester"), default=12
    )
    max_credits_per_semester = models.PositiveSmallIntegerField(
        _("maximum credits per semester"),
        default=24,
        help_text=_("Registration ceiling enforced at course registration (FR-ENR-02)."),
    )

    entry_requirements = models.JSONField(
        _("entry requirements"),
        default=dict,
        blank=True,
        help_text=_(
            "Configurable rules screened against applicants in Phase 2 (FR-ADM-03), "
            'e.g. {"min_certificate_grade": "C", "required_subjects": ["Mathematics"]}.'
        ),
    )
    admission_quota_rules = models.JSONField(
        _("admission quota rules"),
        default=dict,
        blank=True,
        help_text=_(
            "Merit list seat allocation (FR-ADM-06), e.g. "
            '{"total_seats": 50, "reserved": [{"category": "state", "value": '
            '"warrap", "seats": 5}]}. Empty means no cap — every applicant ranks '
            "and none is excluded."
        ),
    )

    description = models.TextField(_("description"), blank=True)
    is_active = models.BooleanField(
        _("accepting students"),
        default=True,
        help_text=_("Turn off to stop admissions without affecting enrolled students."),
    )

    class Meta:
        verbose_name = _("programme")
        verbose_name_plural = _("programmes")
        ordering = ["department__name", "name"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        return super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if self.min_credits_per_semester > self.max_credits_per_semester:
            raise ValidationError(
                {
                    "max_credits_per_semester": _(
                        "The maximum credit load cannot be below the minimum."
                    )
                }
            )

    @property
    def faculty(self) -> Faculty:
        return self.department.faculty

    def current_curriculum(self) -> CurriculumVersion | None:
        return self.curriculum_versions.filter(status=CurriculumStatus.ACTIVE).first()


class CurriculumStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    ACTIVE = "active", _("Active")
    RETIRED = "retired", _("Retired")


class CurriculumVersion(AuditedModel, TimeStampedModel):
    """A dated snapshot of a programme's course requirements (FR-CUR-03)."""

    audit_fields = ("version", "status", "effective_from", "effective_to", "approved_by")

    programme = models.ForeignKey(
        Programme, on_delete=models.CASCADE, related_name="curriculum_versions"
    )
    version = models.CharField(_("version"), max_length=20, help_text=_("e.g. 2026-v1"))
    status = models.CharField(
        _("status"), max_length=10, choices=CurriculumStatus.choices, default=CurriculumStatus.DRAFT
    )

    effective_from = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.PROTECT,
        related_name="curricula_started",
    )
    effective_to = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="curricula_ended",
        help_text=_("Leave empty while this is the version in force."),
    )

    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_curricula",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("curriculum version")
        verbose_name_plural = _("curriculum versions")
        ordering = ["programme__name", "-effective_from__start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["programme", "version"], name="unique_curriculum_version_per_programme"
            ),
            models.UniqueConstraint(
                fields=["programme"],
                condition=models.Q(status="active"),
                name="one_active_curriculum_per_programme",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.programme.code} {self.version}"

    @property
    def total_core_credits(self) -> int:
        return sum(
            entry.course.credit_hours
            for entry in self.courses.filter(is_core=True).select_related("course")
        )

    def credit_shortfall(self) -> int:
        """Core credits still short of the graduation requirement.

        A curriculum whose core courses cannot reach the requirement is a
        configuration error that only surfaces years later, when a final-year
        student cannot graduate.
        """
        return max(0, self.programme.total_credits_required - self.total_core_credits)


class Course(AuditedModel, TimeStampedModel, SoftDeleteModel):
    audit_fields = ("code", "title", "credit_hours", "level", "is_active", "deleted_at")

    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="courses",
        help_text=_("The department that owns and teaches this course."),
    )
    code = models.CharField(_("code"), max_length=20, unique=True)
    title = models.CharField(_("title"), max_length=200)
    description = models.TextField(_("description"), blank=True)

    credit_hours = models.PositiveSmallIntegerField(
        _("credit hours"), validators=[MinValueValidator(1), MaxValueValidator(30)]
    )
    level = models.PositiveSmallIntegerField(
        _("level"),
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text=_("Year of study this course is normally taken in."),
    )
    contact_hours_per_week = models.PositiveSmallIntegerField(default=3)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("course")
        verbose_name_plural = _("courses")
        ordering = ["code"]
        indexes = [models.Index(fields=["department", "level"])]

    def __str__(self) -> str:
        return f"{self.code} — {self.title} ({self.credit_hours} cr)"

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        return super().save(*args, **kwargs)


class CurriculumCourse(TimeStampedModel):
    """Where a course sits in a programme's curriculum (FR-CUR-02)."""

    curriculum_version = models.ForeignKey(
        CurriculumVersion, on_delete=models.CASCADE, related_name="courses"
    )
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="curricula")

    year_of_study = models.PositiveSmallIntegerField(_("year of study"), default=1)
    semester_sequence = models.PositiveSmallIntegerField(_("semester"), default=1)

    is_core = models.BooleanField(
        _("core"), default=True, help_text=_("Core courses are compulsory; others are electives.")
    )
    elective_group = models.CharField(
        _("elective group"),
        max_length=50,
        blank=True,
        help_text=_('For "choose 2 of 4" sets — give the alternatives the same group name.'),
    )
    min_group_choices = models.PositiveSmallIntegerField(
        _("choices required from group"), default=0
    )

    class Meta:
        verbose_name = _("curriculum course")
        verbose_name_plural = _("curriculum courses")
        ordering = ["year_of_study", "semester_sequence", "course__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["curriculum_version", "course"], name="unique_course_per_curriculum"
            ),
        ]

    def __str__(self) -> str:
        kind = _("core") if self.is_core else _("elective")
        return f"{self.curriculum_version} · {self.course.code} (Y{self.year_of_study}, {kind})"

    def clean(self) -> None:
        super().clean()
        if self.curriculum_version_id and self.year_of_study:
            duration = self.curriculum_version.programme.duration_years
            if self.year_of_study > duration:
                raise ValidationError(
                    {
                        "year_of_study": _(
                            "This programme runs for %(years)d year(s), so year "
                            "%(given)d does not exist."
                        )
                        % {"years": duration, "given": self.year_of_study}
                    }
                )
        if not self.is_core and not self.elective_group:
            raise ValidationError(
                {"elective_group": _("Give electives a group name so choices can be counted.")}
            )


class Prerequisite(TimeStampedModel):
    """`course` may not be taken until `required_course` is passed (FR-ENR-02)."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="prerequisites")
    required_course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="required_for"
    )
    minimum_grade_point = models.DecimalField(
        _("minimum grade point"),
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Leave empty to accept any pass."),
    )
    is_concurrent_allowed = models.BooleanField(
        _("may be taken concurrently"),
        default=False,
        help_text=_("Allow registering for both in the same semester."),
    )

    class Meta:
        verbose_name = _("prerequisite")
        verbose_name_plural = _("prerequisites")
        constraints = [
            models.UniqueConstraint(
                fields=["course", "required_course"], name="unique_prerequisite_pair"
            ),
            models.CheckConstraint(
                condition=~models.Q(course=models.F("required_course")),
                name="prerequisite_not_self",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.course.code} requires {self.required_course.code}"

    def clean(self) -> None:
        super().clean()
        if self.course_id and self.required_course_id:
            if self.course_id == self.required_course_id:
                raise ValidationError(_("A course cannot be its own prerequisite."))
            if self._creates_cycle():
                raise ValidationError(
                    _(
                        "This would create a prerequisite cycle: %(required)s already "
                        "depends on %(course)s, so neither could ever be taken."
                    )
                    % {
                        "required": self.required_course.code,
                        "course": self.course.code,
                    }
                )

    def _creates_cycle(self) -> bool:
        """Walk the prerequisite graph upward from `required_course`.

        A cycle makes a programme impossible to complete and is easy to create by
        hand across three or four separate edits, so it is checked on save rather
        than trusted to reviewers.
        """
        target = self.course_id
        seen: set[int] = set()
        frontier = [self.required_course_id]

        while frontier:
            current = frontier.pop()
            if current == target:
                return True
            if current in seen:
                continue
            seen.add(current)
            frontier.extend(
                Prerequisite.objects.filter(course_id=current)
                .exclude(pk=self.pk)
                .values_list("required_course_id", flat=True)
            )

        return False
