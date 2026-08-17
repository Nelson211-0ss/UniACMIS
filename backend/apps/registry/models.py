"""
Core registry: the student and staff records everything else hangs off.

The identifying decisions:

**Student records exist before login accounts do.** `user` is nullable — a
registrar enters an admitted student from a paper form long before that student
ever sees the portal, so names are authoritative here rather than on `User`.

**Statutory reporting fields are constrained choices, not free text.** FR-RPT-03
requires returns disaggregated by gender, disability and state of origin. Free
text makes that aggregation guesswork.

**Nothing is hard-deleted.** Student IDs must never be reused (FR-REG-01), and a
row that can be deleted is a row whose ID can be reissued.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditedModel
from apps.core.choices import Gender, SouthSudanState
from apps.core.models import SoftDeleteModel, TimeStampedModel

__all__ = [
    "AcademicRank",
    "AppointmentType",
    "DocumentType",
    "Gender",
    "NextOfKin",
    "Sponsor",
    "SponsorType",
    "SponsorshipType",
    "StaffCategory",
    "StaffProfile",
    "Student",
    "StudentDocument",
    "StudentStatus",
    "StudentStatusHistory",
]


class StudentStatus(models.TextChoices):
    """FR-REG-04. Every transition is recorded in StudentStatusHistory."""

    ACTIVE = "active", _("Active")
    SUSPENDED = "suspended", _("Suspended")
    DEFERRED = "deferred", _("Deferred")
    WITHDRAWN = "withdrawn", _("Withdrawn")
    GRADUATED = "graduated", _("Graduated")
    EXPELLED = "expelled", _("Expelled")


class SponsorshipType(models.TextChoices):
    """FR-FIN-04 requires sponsored accounts tracked distinctly from
    self-sponsored ones."""

    SELF = "self", _("Self-sponsored")
    GOVERNMENT = "government", _("Government-sponsored")
    SCHOLARSHIP = "scholarship", _("Scholarship")
    BURSARY = "bursary", _("Bursary")
    EMPLOYER = "employer", _("Employer-sponsored")
    NGO = "ngo", _("NGO-sponsored")


class SponsorType(models.TextChoices):
    GOVERNMENT = "government", _("Government")
    NGO = "ngo", _("NGO")
    COMPANY = "company", _("Company")
    INDIVIDUAL = "individual", _("Individual")
    SCHOLARSHIP_FUND = "scholarship_fund", _("Scholarship fund")


class Sponsor(AuditedModel, TimeStampedModel, SoftDeleteModel):
    audit_fields = ("name", "sponsor_type", "is_active", "deleted_at")

    name = models.CharField(_("name"), max_length=200)
    sponsor_type = models.CharField(_("type"), max_length=20, choices=SponsorType.choices)
    contact_person = models.CharField(_("contact person"), max_length=150, blank=True)
    phone = models.CharField(_("phone"), max_length=32, blank=True)
    email = models.EmailField(_("email"), blank=True)
    address = models.TextField(_("address"), blank=True)
    notes = models.TextField(_("notes"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("sponsor")
        verbose_name_plural = _("sponsors")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Student(AuditedModel, TimeStampedModel, SoftDeleteModel):
    audit_fields = (
        "student_id",
        "status",
        "programme",
        "curriculum_version",
        "current_level",
        "sponsorship_type",
        "sponsor",
        "user",
        "deleted_at",
    )

    # ---- identity ----
    student_id = models.CharField(
        _("student ID"),
        max_length=50,
        unique=True,
        help_text=_("Generated from the institution's template. Never reused (FR-REG-01)."),
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_profile",
        help_text=_("Portal login. Empty until the account is activated."),
    )

    # ---- academic placement ----
    programme = models.ForeignKey(
        "curriculum.Programme", on_delete=models.PROTECT, related_name="students"
    )
    curriculum_version = models.ForeignKey(
        "curriculum.CurriculumVersion",
        on_delete=models.PROTECT,
        related_name="students",
        null=True,
        blank=True,
        help_text=_("The syllabus this student is assessed against (FR-CUR-03)."),
    )
    entry_academic_year = models.ForeignKey(
        "academics.AcademicYear", on_delete=models.PROTECT, related_name="entering_students"
    )
    current_level = models.PositiveSmallIntegerField(
        _("year of study"), default=1, validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    status = models.CharField(
        _("status"), max_length=15, choices=StudentStatus.choices, default=StudentStatus.ACTIVE
    )

    # ---- sponsorship ----
    sponsorship_type = models.CharField(
        _("sponsorship"),
        max_length=15,
        choices=SponsorshipType.choices,
        default=SponsorshipType.SELF,
    )
    sponsor = models.ForeignKey(
        Sponsor, on_delete=models.SET_NULL, null=True, blank=True, related_name="students"
    )

    # ---- bio-data (FR-REG-02) ----
    first_name = models.CharField(_("first name"), max_length=100)
    middle_name = models.CharField(_("middle name"), max_length=100, blank=True)
    last_name = models.CharField(_("last name"), max_length=100)
    date_of_birth = models.DateField(_("date of birth"), null=True, blank=True)
    gender = models.CharField(_("gender"), max_length=15, choices=Gender.choices)

    national_id_number = models.CharField(_("national ID number"), max_length=50, blank=True)
    passport_number = models.CharField(_("passport number"), max_length=50, blank=True)
    nationality = models.CharField(_("nationality"), max_length=100, default="South Sudanese")
    state_of_origin = models.CharField(
        _("state of origin"),
        max_length=30,
        choices=SouthSudanState.choices,
        blank=True,
        help_text=_("Required for statutory returns (FR-RPT-03)."),
    )
    county = models.CharField(_("county"), max_length=100, blank=True)

    has_disability = models.BooleanField(_("has a disability"), default=False)
    disability_details = models.TextField(
        _("disability details"),
        blank=True,
        help_text=_("Supports special-needs provision and quota rules."),
    )

    # ---- contact ----
    phone = models.CharField(_("phone"), max_length=32, blank=True)
    alternate_phone = models.CharField(_("alternate phone"), max_length=32, blank=True)
    email = models.EmailField(_("email"), blank=True)
    physical_address = models.TextField(_("address"), blank=True)
    photo = models.ImageField(_("photo"), upload_to="students/photos/", null=True, blank=True)

    # ---- prior study (FR-REG-05) ----
    previous_institution = models.CharField(_("previous institution"), max_length=200, blank=True)
    previous_qualification = models.CharField(
        _("previous qualification"), max_length=200, blank=True
    )
    transfer_credits = models.PositiveSmallIntegerField(_("transfer credits"), default=0)

    admitted_on = models.DateField(_("admitted on"), null=True, blank=True)
    graduated_on = models.DateField(_("graduated on"), null=True, blank=True)

    is_active = models.BooleanField(_("active record"), default=True)

    class Meta:
        verbose_name = _("student")
        verbose_name_plural = _("students")
        ordering = ["last_name", "first_name"]
        indexes = [
            models.Index(fields=["programme", "status"]),
            models.Index(fields=["entry_academic_year", "status"]),
            models.Index(fields=["last_name", "first_name"]),
            models.Index(fields=["national_id_number"]),
            models.Index(fields=["status", "current_level"]),
        ]
        permissions = [
            # Status changes are a separate authority from editing bio-data: a clerk
            # who can correct a misspelled name should not be able to mark a student
            # withdrawn.
            ("change_student_status", _("Can change a student's status")),
        ]

    def __str__(self) -> str:
        return f"{self.student_id} — {self.get_full_name()}"

    def get_full_name(self) -> str:
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(p for p in parts if p).strip()

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        if self.has_disability and not self.disability_details.strip():
            errors["disability_details"] = _(
                "Describe the disability so support and reporting can be provided."
            )

        if self.sponsorship_type != SponsorshipType.SELF and self.sponsor_id is None:
            errors["sponsor"] = _("Name the sponsor for a sponsored student.")

        if (
            self.curriculum_version_id
            and self.programme_id
            and self.curriculum_version.programme_id != self.programme_id
        ):
            errors["curriculum_version"] = _(
                "That curriculum version belongs to a different programme."
            )

        if self.status == StudentStatus.GRADUATED and self.graduated_on is None:
            errors["graduated_on"] = _("Record the graduation date.")

        if errors:
            raise ValidationError(errors)

    @property
    def is_enrolled(self) -> bool:
        return self.status == StudentStatus.ACTIVE


class StudentStatusHistory(TimeStampedModel):
    """Append-only status trail (FR-REG-04).

    Overlaps with the audit log deliberately: this is a *domain* record the
    registrar reads and reports on, and it must survive audit-log archival.
    """

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(
        _("from"), max_length=15, choices=StudentStatus.choices, blank=True
    )
    to_status = models.CharField(_("to"), max_length=15, choices=StudentStatus.choices)
    reason = models.TextField(
        _("reason"),
        help_text=_("Required — a status change without a stated reason is not defensible."),
    )
    effective_date = models.DateField(_("effective date"))
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_status_changes",
    )
    reference = models.CharField(
        _("reference"),
        max_length=100,
        blank=True,
        help_text=_("Minute number or letter reference authorising the change."),
    )

    class Meta:
        verbose_name = _("status change")
        verbose_name_plural = _("status history")
        ordering = ["-effective_date", "-id"]
        indexes = [models.Index(fields=["student", "-effective_date"])]

    def __str__(self) -> str:
        return f"{self.student.student_id}: {self.from_status or '—'} → {self.to_status}"


class NextOfKin(TimeStampedModel):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="next_of_kin")
    full_name = models.CharField(_("full name"), max_length=150)
    relationship = models.CharField(_("relationship"), max_length=50)
    phone = models.CharField(_("phone"), max_length=32)
    alternate_phone = models.CharField(_("alternate phone"), max_length=32, blank=True)
    email = models.EmailField(_("email"), blank=True)
    address = models.TextField(_("address"), blank=True)
    is_primary = models.BooleanField(_("primary contact"), default=False)

    class Meta:
        verbose_name = _("next of kin")
        verbose_name_plural = _("next of kin")
        ordering = ["-is_primary", "full_name"]
        constraints = [
            # Exactly one primary contact: "who do we call?" must have one answer.
            models.UniqueConstraint(
                fields=["student"],
                condition=models.Q(is_primary=True),
                name="one_primary_next_of_kin_per_student",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.relationship})"


class DocumentType(models.TextChoices):
    CERTIFICATE = "certificate", _("Certificate")
    TRANSCRIPT = "transcript", _("Transcript")
    NATIONAL_ID = "national_id", _("National ID")
    PASSPORT = "passport", _("Passport")
    PHOTO = "photo", _("Passport photo")
    MEDICAL_CLEARANCE = "medical_clearance", _("Medical clearance")
    RECOMMENDATION = "recommendation", _("Recommendation letter")
    OTHER = "other", _("Other")


class StudentDocument(TimeStampedModel):
    """Document vault (FR-REG-03).

    `content_hash` is stored so that a file substituted after verification is
    detectable — verifying a certificate means nothing if the file can be swapped
    afterwards.
    """

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(_("type"), max_length=25, choices=DocumentType.choices)
    title = models.CharField(_("title"), max_length=200)
    file = models.FileField(_("file"), upload_to="students/documents/%Y/%m/")
    file_size = models.PositiveIntegerField(_("size (bytes)"), default=0)
    content_hash = models.CharField(_("SHA-256"), max_length=64, blank=True, db_index=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_student_documents",
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_student_documents",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("student document")
        verbose_name_plural = _("student documents")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["student", "document_type"])]
        permissions = [("verify_studentdocument", _("Can verify uploaded student documents"))]

    def __str__(self) -> str:
        return f"{self.get_document_type_display()} — {self.title}"

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None


# --------------------------------------------------------------------- staff


class AppointmentType(models.TextChoices):
    FULL_TIME = "full_time", _("Full-time")
    PART_TIME = "part_time", _("Part-time")
    CONTRACT = "contract", _("Contract")
    VISITING = "visiting", _("Visiting")
    ADJUNCT = "adjunct", _("Adjunct")


class StaffCategory(models.TextChoices):
    ACADEMIC = "academic", _("Academic")
    ADMINISTRATIVE = "administrative", _("Administrative")
    SUPPORT = "support", _("Support")


class AcademicRank(models.TextChoices):
    PROFESSOR = "professor", _("Professor")
    ASSOCIATE_PROFESSOR = "associate_professor", _("Associate Professor")
    SENIOR_LECTURER = "senior_lecturer", _("Senior Lecturer")
    LECTURER = "lecturer", _("Lecturer")
    ASSISTANT_LECTURER = "assistant_lecturer", _("Assistant Lecturer")
    TEACHING_ASSISTANT = "teaching_assistant", _("Teaching Assistant")
    NOT_APPLICABLE = "not_applicable", _("Not applicable")


class StaffProfile(AuditedModel, TimeStampedModel, SoftDeleteModel):
    """Employment record.

    Phase 1 holds the core identity only — contracts, qualifications, leave and
    appraisal belong to `hr` in Phase 5 (FR-HR-01…04). It exists now because
    `Department.head`, `Faculty.dean` and course allocation all point at it.
    """

    audit_fields = (
        "staff_number",
        "department",
        "appointment_type",
        "rank",
        "is_active",
        "deleted_at",
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_profile"
    )
    staff_number = models.CharField(_("staff number"), max_length=50, unique=True)

    department = models.ForeignKey(
        "curriculum.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff",
    )
    staff_category = models.CharField(
        _("category"), max_length=20, choices=StaffCategory.choices, default=StaffCategory.ACADEMIC
    )
    appointment_type = models.CharField(
        _("appointment"),
        max_length=15,
        choices=AppointmentType.choices,
        default=AppointmentType.FULL_TIME,
    )
    rank = models.CharField(
        _("rank"), max_length=25, choices=AcademicRank.choices, default=AcademicRank.LECTURER
    )

    highest_qualification = models.CharField(_("highest qualification"), max_length=200, blank=True)
    date_of_hire = models.DateField(_("date of hire"), null=True, blank=True)
    contract_end_date = models.DateField(_("contract ends"), null=True, blank=True)

    date_of_birth = models.DateField(_("date of birth"), null=True, blank=True)
    gender = models.CharField(_("gender"), max_length=15, choices=Gender.choices, blank=True)
    national_id_number = models.CharField(_("national ID number"), max_length=50, blank=True)
    phone = models.CharField(_("phone"), max_length=32, blank=True)

    is_active = models.BooleanField(_("in service"), default=True)

    class Meta:
        verbose_name = _("staff member")
        verbose_name_plural = _("staff")
        ordering = ["user__last_name", "user__first_name"]
        indexes = [models.Index(fields=["department", "is_active"])]

    def __str__(self) -> str:
        return f"{self.staff_number} — {self.user.get_full_name()}"

    def clean(self) -> None:
        super().clean()
        if (
            self.date_of_hire
            and self.contract_end_date
            and self.contract_end_date <= self.date_of_hire
        ):
            raise ValidationError(
                {"contract_end_date": _("The contract cannot end before it starts.")}
            )
        if self.staff_category != StaffCategory.ACADEMIC and self.rank not in {
            AcademicRank.NOT_APPLICABLE,
            "",
        }:
            raise ValidationError({"rank": _("Academic ranks apply to academic staff only.")})

    def get_full_name(self) -> str:
        return self.user.get_full_name()
