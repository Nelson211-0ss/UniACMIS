"""
Institutional configuration.

NFR-MAINT-03: fee structures, grading scales and the academic calendar are data
the registrar can change, not constants a developer has to redeploy. Everything in
this module exists so that no other module ever hard-codes a date, a grade
boundary or a threshold.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import pairwise

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditedModel
from apps.core.fields import Currency
from apps.core.models import TimeStampedModel

# Bands are expressed to two decimal places (0–49.99, 50–59.99, …), so adjacent
# bands are one step apart. Anything larger is a gap a student's mark could fall
# into with no grade defined.
GRADE_BAND_STEP = Decimal("0.01")


class Institution(TimeStampedModel, AuditedModel):
    """The university. One row in Phase 1 — multi-campus is deferred (D-1)."""

    audit_fields = (
        "name",
        "mohest_code",
        "default_currency",
        "student_id_template",
        "attendance_threshold_percent",
    )

    name = models.CharField(_("name"), max_length=200)
    short_name = models.CharField(_("short name"), max_length=50, blank=True)
    mohest_code = models.CharField(
        _("MoHEST code"),
        max_length=50,
        blank=True,
        help_text=_("Identifier used on statutory returns to the Ministry."),
    )

    default_currency = models.CharField(
        _("base currency"), max_length=3, choices=Currency.choices, default=Currency.SSP
    )
    secondary_currency = models.CharField(
        _("secondary currency"),
        max_length=3,
        choices=Currency.choices,
        blank=True,
        default=Currency.USD,
        help_text=_("Used for fee categories quoted in foreign currency."),
    )

    logo = models.ImageField(_("logo"), upload_to="institution/", blank=True, null=True)
    letterhead = models.FileField(_("letterhead"), upload_to="institution/", blank=True, null=True)

    address = models.TextField(_("address"), blank=True)
    phone = models.CharField(_("phone"), max_length=32, blank=True)
    email = models.EmailField(_("email"), blank=True)
    website = models.URLField(_("website"), blank=True)

    student_id_template = models.CharField(
        _("student ID format"),
        max_length=100,
        default="{faculty}/{programme}/{year}/{seq:04d}",
        help_text=_(
            "Placeholders: {faculty}, {programme}, {year}, {seq}. "
            "Example: ENG/CIV/2026/0042. Changing this does not renumber existing students."
        ),
    )
    staff_id_template = models.CharField(
        _("staff ID format"),
        max_length=100,
        default="STF/{year}/{seq:04d}",
    )

    attendance_threshold_percent = models.DecimalField(
        _("minimum attendance %"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("75.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text=_("Below this, a student may be barred from examinations (FR-ATT-02)."),
    )

    timezone = models.CharField(_("timezone"), max_length=64, default="Africa/Juba")

    class Meta:
        verbose_name = _("institution")
        verbose_name_plural = _("institution")

    def __str__(self) -> str:
        return self.short_name or self.name

    @classmethod
    def get(cls) -> Institution | None:
        """The configured institution, or None if setup has not run."""
        return cls.objects.order_by("pk").first()

    def clean(self) -> None:
        super().clean()
        required = ("{seq", "{year}")
        missing = [token for token in required if token not in self.student_id_template]
        if missing:
            raise ValidationError(
                {
                    "student_id_template": _(
                        "The template must contain %(tokens)s, otherwise generated IDs "
                        "would not be unique."
                    )
                    % {"tokens": ", ".join(f"{t}" + ("}" if t == "{seq" else "") for t in missing)}
                }
            )


class AcademicYear(TimeStampedModel, AuditedModel):
    """e.g. 2026/2027."""

    audit_fields = ("name", "start_date", "end_date", "is_current")

    name = models.CharField(_("name"), max_length=20, unique=True, help_text=_("e.g. 2026/2027"))
    start_date = models.DateField(_("starts"))
    end_date = models.DateField(_("ends"))
    is_current = models.BooleanField(_("current"), default=False)

    class Meta:
        verbose_name = _("academic year")
        verbose_name_plural = _("academic years")
        ordering = ["-start_date"]
        constraints = [
            # Enforced by the database, not only by application code: two current
            # years would make "this year's enrollment" ambiguous everywhere.
            models.UniqueConstraint(
                fields=["is_current"],
                condition=models.Q(is_current=True),
                name="only_one_current_academic_year",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError({"end_date": _("The year must end after it starts.")})


class Semester(TimeStampedModel, AuditedModel):
    """A teaching period, with the windows that govern what may happen when.

    Two per year by default; the count is data, so a trimester institution needs
    no code change (FR-ENR-01).
    """

    audit_fields = (
        "name",
        "teaching_start",
        "teaching_end",
        "registration_opens",
        "registration_closes",
        "is_current",
    )

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="semesters"
    )
    sequence = models.PositiveSmallIntegerField(_("sequence"), default=1)
    name = models.CharField(_("name"), max_length=50, help_text=_("e.g. Semester 1"))

    teaching_start = models.DateField(_("teaching starts"))
    teaching_end = models.DateField(_("teaching ends"))
    exam_start = models.DateField(_("examinations start"), null=True, blank=True)
    exam_end = models.DateField(_("examinations end"), null=True, blank=True)

    registration_opens = models.DateTimeField(_("registration opens"), null=True, blank=True)
    registration_closes = models.DateTimeField(_("registration closes"), null=True, blank=True)
    add_drop_closes = models.DateTimeField(_("add/drop closes"), null=True, blank=True)

    is_current = models.BooleanField(_("current"), default=False)

    class Meta:
        verbose_name = _("semester")
        verbose_name_plural = _("semesters")
        ordering = ["-academic_year__start_date", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "sequence"], name="unique_semester_sequence_per_year"
            ),
            models.UniqueConstraint(
                fields=["is_current"],
                condition=models.Q(is_current=True),
                name="only_one_current_semester",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.academic_year.name} — {self.name}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        if self.teaching_start and self.teaching_end and self.teaching_start > self.teaching_end:
            errors["teaching_end"] = _("Teaching must end after it starts.")

        if self.exam_start and self.exam_end and self.exam_start > self.exam_end:
            errors["exam_end"] = _("Examinations must end after they start.")

        if (
            self.registration_opens
            and self.registration_closes
            and self.registration_opens >= self.registration_closes
        ):
            errors["registration_closes"] = _("Registration must close after it opens.")

        if (
            self.add_drop_closes
            and self.registration_closes
            and self.add_drop_closes < self.registration_closes
        ):
            errors["add_drop_closes"] = _(
                "Add/drop closes before registration does, which would leave students "
                "unable to correct a registration they just made."
            )

        if self.teaching_start and self.academic_year_id:
            year = self.academic_year
            if not (year.start_date <= self.teaching_start <= year.end_date):
                errors["teaching_start"] = _("Teaching must start within the academic year.")

        if errors:
            raise ValidationError(errors)


class GradingScale(TimeStampedModel, AuditedModel):
    """A grading policy: letters, boundaries and grade points (FR-EXM-04)."""

    audit_fields = ("name", "max_grade_point", "pass_grade_point", "is_default", "is_locked")

    name = models.CharField(_("name"), max_length=100, unique=True)
    description = models.TextField(_("description"), blank=True)

    max_grade_point = models.DecimalField(
        _("maximum grade point"),
        max_digits=4,
        decimal_places=2,
        default=Decimal("4.00"),
        help_text=_("4.00 or 5.00 depending on institutional policy."),
    )
    pass_grade_point = models.DecimalField(
        _("minimum passing grade point"),
        max_digits=4,
        decimal_places=2,
        default=Decimal("2.00"),
    )

    is_default = models.BooleanField(_("default scale"), default=False)
    effective_from = models.ForeignKey(
        AcademicYear,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="grading_scales",
        help_text=_("Cohorts before this year keep their own scale."),
    )
    is_locked = models.BooleanField(
        _("locked"),
        default=False,
        help_text=_(
            "Set once results have been published against this scale. A locked "
            "scale cannot be edited, because changing a boundary would silently "
            "rewrite grades already on transcripts."
        ),
    )

    class Meta:
        verbose_name = _("grading scale")
        verbose_name_plural = _("grading scales")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=models.Q(is_default=True),
                name="only_one_default_grading_scale",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @classmethod
    def get_default(cls) -> GradingScale | None:
        return cls.objects.filter(is_default=True).first() or cls.objects.order_by("pk").first()

    def clean(self) -> None:
        super().clean()
        if self.pass_grade_point > self.max_grade_point:
            raise ValidationError(
                {"pass_grade_point": _("The pass mark cannot exceed the maximum grade point.")}
            )

    def validate_bands(self, bands: list[GradeBand] | None = None) -> None:
        """Check that the bands form a complete, non-overlapping cover of 0–100.

        A scale with a gap or an overlap corrupts every transcript it touches, and
        the error stays invisible until a student disputes a mark that fell into
        the hole. So this is strict, and it is unit-tested.
        """
        bands = list(bands if bands is not None else self.bands.all())

        if not bands:
            raise ValidationError(_("A grading scale needs at least one band."))

        ordered = sorted(bands, key=lambda b: b.min_percent)

        for band in ordered:
            if band.min_percent > band.max_percent:
                raise ValidationError(
                    _("Band %(letter)s has its minimum above its maximum.")
                    % {"letter": band.letter}
                )
            if band.grade_point > self.max_grade_point:
                raise ValidationError(
                    _("Band %(letter)s has a grade point above the scale maximum of %(max)s.")
                    % {"letter": band.letter, "max": self.max_grade_point}
                )

        if ordered[0].min_percent != Decimal("0.00"):
            raise ValidationError(
                _("The lowest band must start at 0, otherwise a very low mark has no grade.")
            )

        if ordered[-1].max_percent != Decimal("100.00"):
            raise ValidationError(
                _("The highest band must reach 100, otherwise a full mark has no grade.")
            )

        for lower, upper in pairwise(ordered):
            if upper.min_percent <= lower.max_percent:
                raise ValidationError(
                    _("Bands %(a)s and %(b)s overlap between %(from)s and %(to)s.")
                    % {
                        "a": lower.letter,
                        "b": upper.letter,
                        "from": upper.min_percent,
                        "to": lower.max_percent,
                    }
                )
            if upper.min_percent - lower.max_percent > GRADE_BAND_STEP:
                raise ValidationError(
                    _("Marks between %(from)s and %(to)s fall into no band.")
                    % {"from": lower.max_percent, "to": upper.min_percent}
                )


class GradeBand(TimeStampedModel, AuditedModel):
    """One letter grade and the percentage range that earns it."""

    audit_fields = ("letter", "min_percent", "max_percent", "grade_point", "is_pass")

    scale = models.ForeignKey(GradingScale, on_delete=models.CASCADE, related_name="bands")
    letter = models.CharField(_("letter"), max_length=5)
    min_percent = models.DecimalField(
        _("from %"),
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    max_percent = models.DecimalField(
        _("to %"),
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    grade_point = models.DecimalField(_("grade point"), max_digits=4, decimal_places=2)
    is_pass = models.BooleanField(_("counts as a pass"), default=True)
    description = models.CharField(
        _("description"), max_length=50, blank=True, help_text=_("e.g. Distinction, Pass, Fail")
    )

    class Meta:
        verbose_name = _("grade band")
        verbose_name_plural = _("grade bands")
        ordering = ["scale", "-min_percent"]
        constraints = [
            models.UniqueConstraint(fields=["scale", "letter"], name="unique_letter_per_scale"),
        ]

    def __str__(self) -> str:
        return f"{self.letter} ({self.min_percent}–{self.max_percent}%) = {self.grade_point}"

    def clean(self) -> None:
        super().clean()
        if self.min_percent > self.max_percent:
            raise ValidationError({"max_percent": _("The maximum must be above the minimum.")})
        if self.scale_id and self.scale.is_locked:
            raise ValidationError(
                _(
                    "This grading scale is locked because results have been published "
                    "against it. Create a new scale instead of editing this one."
                )
            )

    def contains(self, percent: Decimal) -> bool:
        return self.min_percent <= percent <= self.max_percent
