"""
Human resources: contracts, leave and appraisal (FR-HR-01…04).

Payroll computation is explicitly out of scope (SRS §1.2) — `export_payroll`
produces the figures a payroll system needs, never computes a net pay.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditedModel
from apps.core.fields import CurrencyField, MoneyAmountField
from apps.core.models import TimeStampedModel

__all__ = [
    "Appraisal",
    "Contract",
    "ContractType",
    "LeaveRequest",
    "LeaveStatus",
    "LeaveType",
]


class ContractType(models.TextChoices):
    PERMANENT = "permanent", _("Permanent")
    FIXED_TERM = "fixed_term", _("Fixed term")
    PROBATION = "probation", _("Probation")
    PART_TIME = "part_time", _("Part time")


class Contract(AuditedModel, TimeStampedModel):
    """FR-HR-01. One employment contract for a staff member — a new contract
    (renewal, promotion, a change in terms) is a new row, never an edit of
    the old one, so the history a payroll export or a dispute needs stays
    intact."""

    audit_fields = ("contract_type", "basic_salary", "is_active")
    audit_sensitive = True

    staff = models.ForeignKey(
        "registry.StaffProfile", on_delete=models.PROTECT, related_name="contracts"
    )
    contract_type = models.CharField(_("type"), max_length=15, choices=ContractType.choices)
    position = models.CharField(_("position"), max_length=100)
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"), null=True, blank=True)
    basic_salary = MoneyAmountField(_("basic salary"))
    currency = CurrencyField()
    is_active = models.BooleanField(_("active"), default=True)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("contract")
        verbose_name_plural = _("contracts")
        ordering = ["-start_date"]
        permissions = [
            ("export_payroll", _("Can export the payroll-ready contract list")),
        ]

    def clean(self) -> None:
        super().clean()
        if self.contract_type != ContractType.PERMANENT and self.end_date is None:
            raise ValidationError(
                {"end_date": _("Required for anything other than a permanent contract.")}
            )
        if self.end_date is not None and self.end_date <= self.start_date:
            raise ValidationError({"end_date": _("Must be after the start date.")})

    def __str__(self) -> str:
        return f"{self.staff_id} · {self.position} [{self.contract_type}]"


class LeaveType(models.TextChoices):
    ANNUAL = "annual", _("Annual")
    SICK = "sick", _("Sick")
    MATERNITY = "maternity", _("Maternity")
    PATERNITY = "paternity", _("Paternity")
    STUDY = "study", _("Study")
    UNPAID = "unpaid", _("Unpaid")


class LeaveStatus(models.TextChoices):
    SUBMITTED = "submitted", _("Submitted")
    ENDORSED = "endorsed", _("Endorsed by supervisor")
    APPROVED = "approved", _("Approved")
    REJECTED = "rejected", _("Rejected")


class LeaveRequest(AuditedModel, TimeStampedModel):
    """FR-HR-02. Two-level approval: the department head endorses, HR gives
    the final decision — the same "whoever asks is never whoever decides"
    separation every approval workflow in this system uses."""

    audit_fields = ("status",)
    audit_sensitive = True

    staff = models.ForeignKey(
        "registry.StaffProfile", on_delete=models.PROTECT, related_name="leave_requests"
    )
    leave_type = models.CharField(_("type"), max_length=15, choices=LeaveType.choices)
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"))
    reason = models.TextField(_("reason"))
    status = models.CharField(
        _("status"), max_length=15, choices=LeaveStatus.choices, default=LeaveStatus.SUBMITTED
    )

    endorsed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    endorsed_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    decision_notes = models.TextField(_("decision notes"), blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("leave request")
        verbose_name_plural = _("leave requests")
        ordering = ["-created_at"]
        permissions = [
            ("approve_leaverequest", _("Can give the final decision on a leave request")),
        ]

    def clean(self) -> None:
        super().clean()
        if self.end_date < self.start_date:
            raise ValidationError({"end_date": _("Must not be before the start date.")})

    def __str__(self) -> str:
        return f"{self.staff_id} · {self.leave_type} [{self.status}]"


class Appraisal(AuditedModel, TimeStampedModel):
    """FR-HR-03. Conducted by the staff member's department head — HR's
    permission is deliberately view/change only, never add: it is not who
    the policy has doing the reviewing."""

    audit_fields = ("rating", "promotion_recommended")
    audit_sensitive = True

    staff = models.ForeignKey(
        "registry.StaffProfile", on_delete=models.PROTECT, related_name="appraisals"
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear", on_delete=models.PROTECT, related_name="appraisals"
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    rating = models.PositiveSmallIntegerField(
        _("rating"), help_text=_("1 (unsatisfactory) to 5 (outstanding).")
    )
    comments = models.TextField(_("comments"), blank=True)
    promotion_recommended = models.BooleanField(_("promotion recommended"), default=False)

    class Meta:
        verbose_name = _("appraisal")
        verbose_name_plural = _("appraisals")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "academic_year"], name="one_appraisal_per_staff_per_year"
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.rating is not None and not (1 <= self.rating <= 5):
            raise ValidationError({"rating": _("Must be between 1 and 5.")})

    def __str__(self) -> str:
        return f"{self.staff_id} · {self.academic_year_id} · {self.rating}/5"
