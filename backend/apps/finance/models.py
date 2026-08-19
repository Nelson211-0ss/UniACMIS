"""
Finance: fee structures, invoicing, payments, scholarships and refunds
(FR-FIN-01…08).

Money is never a bare decimal (`apps.core.fields.MoneyMixin` on every model
that holds an amount) and every write here is `audit_sensitive` — a mark can
be re-derived from its components, a mis-recorded payment cannot.

`Invoice`/`Payment` deliberately carry no "instalment schedule": a partial
payment is just another `Payment` row against the same invoice, and the
balance (`services.invoice_balance`) is always the true remaining amount —
FR-FIN-05's "instalments with balance tracking" without a second model to
keep in sync with the first. A fixed due-date-per-instalment schedule is not
built; see D-11 in `docs/TRACEABILITY.md`.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditedModel
from apps.core.choices import Residency
from apps.core.fields import CurrencyField, MoneyAmountField
from apps.core.models import TimeStampedModel

__all__ = [
    "CoverageType",
    "FeeStructure",
    "Invoice",
    "InvoiceStatus",
    "Payment",
    "PaymentMethod",
    "PaymentStatus",
    "Refund",
    "RefundStatus",
    "Scholarship",
]


class FeeStructure(AuditedModel, TimeStampedModel):
    """What a programme/level/residency combination owes for a semester
    (FR-FIN-01). Data, not a constant — a registrar-adjacent finance officer
    edits these rows when fees change, never a developer."""

    audit_fields = ("amount", "currency", "is_active")

    programme = models.ForeignKey(
        "curriculum.Programme", on_delete=models.PROTECT, related_name="fee_structures"
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear", on_delete=models.PROTECT, related_name="fee_structures"
    )
    level = models.PositiveSmallIntegerField(
        _("year of study"), validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    residency = models.CharField(_("residency"), max_length=15, choices=Residency.choices)

    amount = MoneyAmountField(_("amount per semester"))
    currency = CurrencyField()
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("fee structure")
        verbose_name_plural = _("fee structures")
        ordering = ["academic_year", "programme", "level"]
        constraints = [
            models.UniqueConstraint(
                fields=["programme", "academic_year", "level", "residency"],
                name="one_fee_structure_per_programme_year_level_residency",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.programme_id} · L{self.level} · {self.residency} · {self.amount} {self.currency}"


class InvoiceStatus(models.TextChoices):
    ISSUED = "issued", _("Issued")
    PARTIALLY_PAID = "partially_paid", _("Partially paid")
    PAID = "paid", _("Paid")
    CANCELLED = "cancelled", _("Cancelled")
    WRITTEN_OFF = "written_off", _("Written off")


class Invoice(AuditedModel, TimeStampedModel):
    """One semester's bill for one student (FR-FIN-02)."""

    audit_fields = ("amount", "discount_amount", "status")
    audit_sensitive = True

    student = models.ForeignKey(
        "registry.Student", on_delete=models.PROTECT, related_name="invoices"
    )
    semester = models.ForeignKey(
        "academics.Semester", on_delete=models.PROTECT, related_name="invoices"
    )
    fee_structure = models.ForeignKey(
        FeeStructure, on_delete=models.PROTECT, null=True, blank=True, related_name="invoices"
    )
    invoice_number = models.CharField(_("invoice number"), max_length=40, unique=True)

    amount = MoneyAmountField(_("amount"))
    discount_amount = MoneyAmountField(_("discount"), default=Decimal("0"))
    currency = CurrencyField()

    status = models.CharField(
        _("status"), max_length=15, choices=InvoiceStatus.choices, default=InvoiceStatus.ISSUED
    )
    due_date = models.DateField(_("due date"))
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = _("invoice")
        verbose_name_plural = _("invoices")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "semester"], name="one_invoice_per_student_per_semester"
            ),
        ]
        indexes = [
            models.Index(fields=["student", "status"]),
            models.Index(fields=["semester", "status"]),
        ]
        permissions = [
            ("view_defaulterreport", _("Can view the fee-defaulter report")),
        ]

    def clean(self) -> None:
        super().clean()
        if (
            self.discount_amount is not None
            and self.amount is not None
            and self.discount_amount > self.amount
        ):
            raise ValidationError(
                {"discount_amount": _("The discount cannot exceed the invoiced amount.")}
            )

    @property
    def net_amount(self) -> Decimal:
        return self.amount - self.discount_amount

    def __str__(self) -> str:
        return f"{self.invoice_number} — {self.student_id}"


class PaymentMethod(models.TextChoices):
    MOBILE_MONEY = "mobile_money", _("Mobile money")
    BANK_SLIP = "bank_slip", _("Bank slip")
    CASH = "cash", _("Cash")
    CHEQUE = "cheque", _("Cheque")


class PaymentStatus(models.TextChoices):
    """Deliberately the same strings as `apps.core.ports.PaymentState` — a
    mobile-money payment's status is set directly from what the provider
    says, with no separate mapping table to fall out of sync."""

    PENDING = "pending", _("Pending")
    CONFIRMED = "confirmed", _("Confirmed")
    FAILED = "failed", _("Failed")
    CANCELLED = "cancelled", _("Cancelled")


class Payment(AuditedModel, TimeStampedModel):
    """One payment against an invoice — mobile money via `PaymentProvider`,
    or cash/cheque/bank-slip recorded and reconciled by hand (FR-FIN-03)."""

    audit_fields = ("amount", "status", "receipt_number")
    audit_sensitive = True

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(_("method"), max_length=15, choices=PaymentMethod.choices)
    amount = MoneyAmountField(_("amount"))
    currency = CurrencyField()

    # `provider`/`reference` together identify the transaction: a provider
    # name + its own reference for mobile money, or blank provider + a
    # manually-entered slip/cheque number for the desk-recorded methods.
    provider = models.CharField(_("provider"), max_length=50, blank=True)
    reference = models.CharField(_("reference"), max_length=120, unique=True)

    status = models.CharField(
        _("status"), max_length=15, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    # `null=True` so the database's unique index — which treats every `''` as
    # a duplicate of every other — never sees two unconfirmed payments as a
    # collision. `blank=True` is also required: without it, `full_clean()`
    # rejects the unset value with "This field cannot be blank" regardless of
    # `null`, which governs the database column, not model-level validation.
    # Safe here because every place this field is exposed (the admin, the
    # API serializer) treats it as read-only — nothing ever submits `''`.
    receipt_number = models.CharField(
        _("receipt number"), max_length=40, unique=True, null=True, blank=True
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["invoice", "status"]),
            models.Index(fields=["method", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.reference} — {self.amount} {self.currency} [{self.status}]"


class CoverageType(models.TextChoices):
    PERCENTAGE = "percentage", _("Percentage of fees")
    FIXED_AMOUNT = "fixed_amount", _("Fixed amount")


class Scholarship(AuditedModel, TimeStampedModel):
    """A scholarship/bursary/sponsor award reducing what a student is billed
    (FR-FIN-04) — distinct from `registry.Sponsor`, which is just who the
    funder is; this is how much they cover, for which year."""

    audit_fields = ("coverage_type", "percentage", "fixed_amount", "is_active")
    audit_sensitive = True

    student = models.ForeignKey(
        "registry.Student", on_delete=models.PROTECT, related_name="scholarships"
    )
    sponsor = models.ForeignKey(
        "registry.Sponsor",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="scholarships",
        help_text=_("Left blank for an institution-funded bursary."),
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear", on_delete=models.PROTECT, related_name="scholarships"
    )
    coverage_type = models.CharField(_("coverage"), max_length=15, choices=CoverageType.choices)
    percentage = models.DecimalField(
        _("coverage %"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    fixed_amount = MoneyAmountField(_("fixed amount"), null=True, blank=True)
    currency = CurrencyField()
    is_active = models.BooleanField(_("active"), default=True)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("scholarship")
        verbose_name_plural = _("scholarships")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "academic_year"], name="one_scholarship_per_student_per_year"
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.coverage_type == CoverageType.PERCENTAGE and self.percentage is None:
            raise ValidationError({"percentage": _("Required for percentage coverage.")})
        if self.coverage_type == CoverageType.FIXED_AMOUNT and self.fixed_amount is None:
            raise ValidationError({"fixed_amount": _("Required for fixed-amount coverage.")})

    def discount_for(self, amount: Decimal) -> Decimal:
        """The discount this scholarship applies to an invoice of `amount`,
        capped so it can never make an invoice negative."""
        if not self.is_active:
            return Decimal("0")
        if self.coverage_type == CoverageType.PERCENTAGE:
            discount = (amount * self.percentage / Decimal("100")).quantize(Decimal("0.01"))
        else:
            discount = self.fixed_amount or Decimal("0")
        return min(discount, amount)

    def __str__(self) -> str:
        return f"{self.student_id} · {self.academic_year_id} · {self.coverage_type}"


class RefundStatus(models.TextChoices):
    REQUESTED = "requested", _("Requested")
    APPROVED = "approved", _("Approved")
    REJECTED = "rejected", _("Rejected")
    PAID = "paid", _("Paid")


class Refund(AuditedModel, TimeStampedModel):
    """A request to return money already paid, with approval controls
    (FR-FIN-08) — whoever requests it is deliberately never the same
    permission that approves it."""

    audit_fields = ("amount", "status")
    audit_sensitive = True

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")
    amount = MoneyAmountField(_("amount"))
    currency = CurrencyField()
    reason = models.TextField(_("reason"))
    status = models.CharField(
        _("status"), max_length=15, choices=RefundStatus.choices, default=RefundStatus.REQUESTED
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    decision_notes = models.TextField(_("decision notes"), blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("refund")
        verbose_name_plural = _("refunds")
        ordering = ["-created_at"]
        permissions = [
            ("approve_refund", _("Can approve or reject a refund request")),
        ]

    def __str__(self) -> str:
        return f"Refund {self.amount} {self.currency} on payment {self.payment_id} [{self.status}]"
