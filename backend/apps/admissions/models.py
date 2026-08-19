"""
Admissions: application intake through to conversion into a student record.

FR-ADM-01…08. Bio-data lives on `Application` itself rather than on `User` —
the same choice Phase 1 made for `Student`, and for the same reason: a walk-in
applicant entered from a paper form (FR-ADM-02) has no account yet, and the
record has to be complete regardless.

`Application` is marked `audit_sensitive`: the checklist names admissions fraud
in the same breath as grading and fee fraud (§1), so an admission decision gets
the same transactional audit guarantee a grade change does — if the audit write
fails, the decision itself rolls back.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditedModel
from apps.core.choices import Gender, SouthSudanState
from apps.core.fields import MoneyMixin
from apps.core.models import SoftDeleteModel, TimeStampedModel

__all__ = [
    "Application",
    "ApplicationDocument",
    "ApplicationFeePayment",
    "ApplicationReview",
    "ApplicationSource",
    "ApplicationStatus",
    "FeePaymentStatus",
]


class ApplicationStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    SUBMITTED = "submitted", _("Submitted")
    UNDER_REVIEW = "under_review", _("Under review")
    OFFERED = "offered", _("Offer made")
    ACCEPTED = "accepted", _("Offer accepted")
    REJECTED = "rejected", _("Rejected")
    WITHDRAWN = "withdrawn", _("Withdrawn")
    ENROLLED = "enrolled", _("Converted to student record")


class ApplicationSource(models.TextChoices):
    SELF_SERVICE = "self_service", _("Applicant portal")
    STAFF_ENTRY = "staff_entry", _("Entered by staff (FR-ADM-02)")


class Application(AuditedModel, TimeStampedModel, SoftDeleteModel):
    audit_fields = ("status", "score", "programme", "fee_paid")
    audit_sensitive = True

    reference_number = models.CharField(
        _("reference number"),
        max_length=30,
        unique=True,
        help_text=_("Generated on creation. Given to the applicant to track status."),
    )

    # Nullable exactly as Student.user is: an application entered from a paper
    # form has no portal account yet, and a self-service applicant may abandon
    # a draft before finishing registration.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applications",
    )
    programme = models.ForeignKey(
        "curriculum.Programme", on_delete=models.PROTECT, related_name="applications"
    )
    intended_academic_year = models.ForeignKey(
        "academics.AcademicYear", on_delete=models.PROTECT, related_name="applications"
    )

    # ---- bio-data (mirrors registry.Student's own fields; FR-ADM-01) ----
    first_name = models.CharField(_("first name"), max_length=100)
    middle_name = models.CharField(_("middle name"), max_length=100, blank=True)
    last_name = models.CharField(_("last name"), max_length=100)
    date_of_birth = models.DateField(_("date of birth"), null=True, blank=True)
    gender = models.CharField(_("gender"), max_length=15, choices=Gender.choices)
    nationality = models.CharField(_("nationality"), max_length=100, default="South Sudanese")
    phone = models.CharField(_("phone"), max_length=32, blank=True)
    email = models.EmailField(_("email"), blank=True)
    national_id_number = models.CharField(_("national ID number"), max_length=50, blank=True)
    state_of_origin = models.CharField(
        _("state of origin"), max_length=30, choices=SouthSudanState.choices, blank=True
    )
    county = models.CharField(_("county"), max_length=100, blank=True)
    has_disability = models.BooleanField(_("has a disability"), default=False)
    disability_details = models.TextField(_("disability details"), blank=True)
    physical_address = models.TextField(_("address"), blank=True)

    previous_institution = models.CharField(_("previous institution"), max_length=200, blank=True)
    previous_qualification = models.CharField(
        _("previous qualification"), max_length=200, blank=True
    )
    previous_grade = models.CharField(
        _("previous certificate grade"),
        max_length=10,
        blank=True,
        help_text=_("Screened against the programme's entry requirements (FR-ADM-03)."),
    )

    status = models.CharField(
        _("status"),
        max_length=15,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.DRAFT,
    )
    source = models.CharField(
        _("source"),
        max_length=15,
        choices=ApplicationSource.choices,
        default=ApplicationSource.SELF_SERVICE,
    )
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applications_entered",
        help_text=_("Staff member who typed this in, for staff-entry applications."),
    )

    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(
        _("score"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Average of reviewer scores (FR-ADM-05)."),
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applications_decided",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(_("decision reason"), blank=True)

    fee_paid = models.BooleanField(
        _("application fee paid"),
        default=False,
        help_text=_("Must be true before the application can be submitted (FR-ADM-04)."),
    )

    # Traceable link once FR-ADM-08 conversion happens.
    student = models.OneToOneField(
        "registry.Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="application",
    )

    class Meta:
        verbose_name = _("application")
        verbose_name_plural = _("applications")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["programme", "intended_academic_year", "status"]),
            models.Index(fields=["status"]),
        ]
        permissions = [
            ("decide_application", _("Can accept or reject an application")),
        ]

    def __str__(self) -> str:
        return f"{self.reference_number} — {self.get_full_name()}"

    def get_full_name(self) -> str:
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(p for p in parts if p).strip()

    def clean(self) -> None:
        super().clean()
        if self.has_disability and not self.disability_details.strip():
            raise ValidationError(
                {"disability_details": _("Describe the disability so support can be arranged.")}
            )


class DocumentType(models.TextChoices):
    CERTIFICATE = "certificate", _("Certificate")
    NATIONAL_ID = "national_id", _("National ID")
    PASSPORT = "passport", _("Passport")
    PHOTO = "photo", _("Passport photo")
    RECOMMENDATION = "recommendation", _("Recommendation letter")
    OTHER = "other", _("Other")


class ApplicationDocument(TimeStampedModel):
    """Document upload (FR-ADM-01). Mirrors registry.StudentDocument, including
    the content hash that makes a later substitution detectable."""

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(_("type"), max_length=20, choices=DocumentType.choices)
    title = models.CharField(_("title"), max_length=200)
    file = models.FileField(_("file"), upload_to="admissions/documents/%Y/%m/")
    file_size = models.PositiveIntegerField(default=0)
    content_hash = models.CharField(max_length=64, blank=True, db_index=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_application_documents",
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("application document")
        verbose_name_plural = _("application documents")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_document_type_display()} — {self.title}"


class ApplicationReview(TimeStampedModel):
    """One reviewer's score against the admissions committee's rubric
    (FR-ADM-05). A reviewer re-scoring updates their own row rather than
    piling up duplicates — `record_review` upserts on this constraint."""

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    score = models.DecimalField(_("score"), max_digits=6, decimal_places=2)
    criteria = models.JSONField(
        _("criteria"),
        default=dict,
        blank=True,
        help_text=_('Configurable per-criterion breakdown, e.g. {"academic": 8, "interview": 7}.'),
    )
    comments = models.TextField(_("comments"), blank=True)

    class Meta:
        verbose_name = _("application review")
        verbose_name_plural = _("application reviews")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["application", "reviewer"], name="one_review_per_reviewer"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.application.reference_number}: {self.reviewer} scored {self.score}"


class FeePaymentStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    CONFIRMED = "confirmed", _("Confirmed")
    FAILED = "failed", _("Failed")


class ApplicationFeePayment(MoneyMixin, TimeStampedModel):
    """Application fee record (FR-ADM-04), through the Phase 1 PaymentProvider
    interface — the same mock that lets finance flows be built in Phase 4
    before any mobile-money credentials exist."""

    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="fee_payments"
    )
    provider = models.CharField(max_length=50)
    reference = models.CharField(max_length=100, unique=True)
    status = models.CharField(
        max_length=15, choices=FeePaymentStatus.choices, default=FeePaymentStatus.PENDING
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("application fee payment")
        verbose_name_plural = _("application fee payments")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.reference} ({self.status})"
