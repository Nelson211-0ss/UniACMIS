"""Library catalogue and circulation (FR-LIB-01…03)."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditedModel
from apps.core.fields import CurrencyField, MoneyAmountField
from apps.core.models import SoftDeleteModel, TimeStampedModel

__all__ = ["ItemType", "LibraryItem", "LibraryPolicy", "Loan", "LoanStatus"]


class ItemType(models.TextChoices):
    BOOK = "book", _("Book")
    JOURNAL = "journal", _("Journal")
    EBOOK = "ebook", _("E-book")
    THESIS = "thesis", _("Thesis")
    OTHER = "other", _("Other")


class LibraryItem(AuditedModel, TimeStampedModel, SoftDeleteModel):
    """FR-LIB-01: physical and electronic resources in one catalogue."""

    audit_fields = ("title", "total_copies", "is_active", "deleted_at")

    title = models.CharField(_("title"), max_length=300)
    author = models.CharField(_("author"), max_length=200, blank=True)
    isbn = models.CharField(_("ISBN"), max_length=20, blank=True)
    item_type = models.CharField(_("type"), max_length=15, choices=ItemType.choices)
    is_electronic = models.BooleanField(_("electronic"), default=False)
    resource_url = models.URLField(_("resource URL"), blank=True)
    total_copies = models.PositiveSmallIntegerField(_("total copies"), default=1)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("library item")
        verbose_name_plural = _("library items")
        ordering = ["title"]

    def clean(self) -> None:
        super().clean()
        if self.is_electronic and not self.resource_url:
            raise ValidationError({"resource_url": _("Required for an electronic item.")})

    @property
    def copies_on_loan(self) -> int:
        return self.loans.filter(status=LoanStatus.ACTIVE).count()

    @property
    def available_copies(self) -> int:
        return max(0, self.total_copies - self.copies_on_loan)

    def __str__(self) -> str:
        return self.title


class LoanStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    RETURNED = "returned", _("Returned")
    LOST = "lost", _("Lost")


class Loan(AuditedModel, TimeStampedModel):
    """FR-LIB-02. Exactly one of `borrower_student`/`borrower_staff` is set —
    a loan always has exactly one real person on the other end of it."""

    audit_fields = ("status", "fine_amount", "fine_waived")
    audit_sensitive = True

    item = models.ForeignKey(LibraryItem, on_delete=models.PROTECT, related_name="loans")
    borrower_student = models.ForeignKey(
        "registry.Student",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="library_loans",
    )
    borrower_staff = models.ForeignKey(
        "registry.StaffProfile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="library_loans",
    )
    due_date = models.DateField(_("due date"))
    returned_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        _("status"), max_length=15, choices=LoanStatus.choices, default=LoanStatus.ACTIVE
    )

    fine_amount = MoneyAmountField(_("fine"), default=Decimal("0"))
    currency = CurrencyField()
    fine_waived = models.BooleanField(_("fine waived"), default=False)
    waived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    waived_reason = models.TextField(_("waiver reason"), blank=True)

    class Meta:
        verbose_name = _("loan")
        verbose_name_plural = _("loans")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["item", "status"]),
            models.Index(fields=["borrower_student", "status"]),
            models.Index(fields=["borrower_staff", "status"]),
        ]
        permissions = [
            ("waive_fine", _("Can waive an overdue fine")),
        ]

    def clean(self) -> None:
        super().clean()
        if bool(self.borrower_student_id) == bool(self.borrower_staff_id):
            raise ValidationError(
                _("A loan must have exactly one borrower — a student or a staff member.")
            )

    @property
    def owed(self) -> Decimal:
        return Decimal("0") if self.fine_waived else self.fine_amount

    def __str__(self) -> str:
        return (
            f"{self.item_id} → {self.borrower_student_id or self.borrower_staff_id} [{self.status}]"
        )


class LibraryPolicy(models.Model):
    """A singleton, the same shape as `academics.Institution` — the loan
    period and fine rate are data a librarian edits, never a constant."""

    loan_period_days = models.PositiveSmallIntegerField(_("loan period (days)"), default=14)
    daily_fine_rate = MoneyAmountField(_("daily fine rate"), default=Decimal("0"))
    currency = CurrencyField()

    class Meta:
        verbose_name = _("library policy")
        verbose_name_plural = _("library policy")

    def __str__(self) -> str:
        return f"{self.loan_period_days} days · {self.daily_fine_rate} {self.currency}/day"

    @classmethod
    def get(cls) -> LibraryPolicy | None:
        return cls.objects.first()
