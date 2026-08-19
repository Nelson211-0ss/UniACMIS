"""
Finance services (FR-FIN-01…08).

Cross-currency arithmetic between an invoice and a payment against it is
deliberately not supported: a payment must be recorded in the invoice's own
currency, full stop. `apps.core.fields.Money` refuses to combine currencies
without an explicit rate for exactly this reason, and converting one on the
fly here would be inventing an exchange rate no one actually quoted. A
genuinely foreign-currency payment is recorded as its SSP equivalent by
whoever takes it, the same way a bank teller would.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.academics.services import calendar
from apps.academics.services import config as academics_config
from apps.core.exceptions import ConfigurationError, DomainError
from apps.core.ports import PaymentState
from apps.core.providers import get_payment_provider
from apps.enrollment.services import students_registered_in
from apps.finance.id_generation import generate_invoice_number, generate_receipt_number
from apps.finance.models import (
    FeeStructure,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Refund,
    RefundStatus,
    Scholarship,
)
from apps.hostel.services import fee_for_active_allocation
from apps.registry.services import (
    current_level_for_student,
    get_programme_id,
    residency_for_student,
)


class DuplicateInvoice(DomainError):
    code = "duplicate_invoice"
    message = "This student already has an invoice for this semester."
    status_code = 409


class InvalidPaymentMethod(DomainError):
    code = "invalid_payment_method"


class PaymentNotConfirmed(DomainError):
    code = "payment_not_confirmed"
    message = "Only a confirmed payment can be refunded."
    status_code = 409


class RefundExceedsPayment(DomainError):
    code = "refund_exceeds_payment"
    status_code = 409


class InvalidRefundTransition(DomainError):
    code = "invalid_refund_transition"
    status_code = 409


class ReasonRequired(DomainError):
    code = "reason_required"


# --------------------------------------------------------------- fee structures


@transaction.atomic
def create_fee_structure(
    *,
    programme_id: int,
    academic_year_id: int,
    level: int,
    residency: str,
    amount: Decimal,
    currency: str | None = None,
    actor: Any = None,
) -> FeeStructure:
    structure = FeeStructure(
        programme_id=programme_id,
        academic_year_id=academic_year_id,
        level=level,
        residency=residency,
        amount=amount,
        currency=currency or academics_config.base_currency(),
    )
    structure.audit_reason = "Fee structure created"
    structure.full_clean()
    structure.save()
    return structure


@transaction.atomic
def update_fee_structure(
    structure: FeeStructure,
    *,
    amount: Decimal | None = None,
    is_active: bool | None = None,
    actor: Any = None,
) -> FeeStructure:
    if amount is not None:
        structure.amount = amount
    if is_active is not None:
        structure.is_active = is_active
    structure.audit_reason = "Fee structure updated"
    structure.full_clean()
    structure.save()
    return structure


def _applicable_fee_structure(
    *, programme_id: int, academic_year_id: int, level: int, residency: str
) -> FeeStructure:
    structure = FeeStructure.objects.filter(
        programme_id=programme_id,
        academic_year_id=academic_year_id,
        level=level,
        residency=residency,
        is_active=True,
    ).first()
    if structure is None:
        raise ConfigurationError(
            "No active fee structure is configured for this programme, year and residency."
        )
    return structure


# ------------------------------------------------------------------- invoicing


@transaction.atomic
def generate_invoice(
    *, student_id: int, semester_id: int, due_date: date | None = None, actor: Any = None
) -> Invoice:
    """FR-FIN-02. One invoice per student per semester, its amount taken from
    the fee structure that matches their programme/level/residency, topped
    up with a flat hostel fee if the student holds an active room allocation
    for the semester's academic year (FR-HOS-03), and reduced by any active
    scholarship for that academic year — the discount applies to the tuition
    component only, since `Scholarship.coverage_type` does not yet
    distinguish what it covers (see D-16 in `docs/TRACEABILITY.md`)."""
    if Invoice.objects.filter(student_id=student_id, semester_id=semester_id).exists():
        raise DuplicateInvoice()

    semester = calendar.get_semester(semester_id)
    programme_id = get_programme_id(student_id)
    level = current_level_for_student(student_id)
    residency = residency_for_student(student_id)

    structure = _applicable_fee_structure(
        programme_id=programme_id,
        academic_year_id=semester.academic_year_id,
        level=level,
        residency=residency,
    )
    hostel_fee = fee_for_active_allocation(
        student_id=student_id, academic_year_id=semester.academic_year_id
    )

    scholarship = Scholarship.objects.filter(
        student_id=student_id, academic_year_id=semester.academic_year_id, is_active=True
    ).first()
    discount = scholarship.discount_for(structure.amount) if scholarship else Decimal("0")

    invoice = Invoice(
        student_id=student_id,
        semester_id=semester_id,
        fee_structure=structure,
        invoice_number=generate_invoice_number(
            calendar.academic_year_name(semester.academic_year_id)
        ),
        amount=structure.amount + hostel_fee,
        discount_amount=discount,
        currency=structure.currency,
        due_date=due_date or semester.teaching_end,
        issued_by=actor if getattr(actor, "pk", None) else None,
    )
    invoice.audit_reason = "Invoice issued"
    invoice.full_clean()
    invoice.save()
    return invoice


def generate_invoices_for_semester(*, semester_id: int, actor: Any = None) -> dict[str, Any]:
    """Batch-runs `generate_invoice` for every student registered this
    semester. Skips (rather than fails) a student who already has one, or
    whose fee structure is not configured yet — both are reported, not
    silently dropped, so the office running the batch knows what needs
    fixing before term starts."""
    created: list[Invoice] = []
    skipped: list[dict[str, Any]] = []
    for student_id in sorted(students_registered_in(semester_id)):
        try:
            created.append(
                generate_invoice(student_id=student_id, semester_id=semester_id, actor=actor)
            )
        except DuplicateInvoice:
            skipped.append({"student_id": student_id, "reason": "duplicate_invoice"})
        except ConfigurationError as exc:
            skipped.append({"student_id": student_id, "reason": str(exc)})
    return {"created": len(created), "skipped": skipped}


def invoice_balance(invoice: Invoice) -> Decimal:
    paid = invoice.payments.filter(status=PaymentStatus.CONFIRMED).aggregate(total=Sum("amount"))[
        "total"
    ] or Decimal("0")
    return invoice.net_amount - paid


def _refresh_invoice_status(invoice: Invoice) -> None:
    balance = invoice_balance(invoice)
    if invoice.status in {InvoiceStatus.CANCELLED, InvoiceStatus.WRITTEN_OFF}:
        return
    new_status = (
        InvoiceStatus.PAID
        if balance <= 0
        else InvoiceStatus.PARTIALLY_PAID if balance < invoice.net_amount else InvoiceStatus.ISSUED
    )
    if new_status != invoice.status:
        invoice.status = new_status
        invoice.audit_reason = f"Balance now {balance} {invoice.currency}"
        invoice.save()


# --------------------------------------------------------------------- payments


@transaction.atomic
def record_manual_payment(
    *,
    invoice_id: int,
    method: str,
    amount: Decimal,
    reference: str,
    actor: Any,
    notes: str = "",
) -> Payment:
    """FR-FIN-03: cash, cheque or a bank slip, recorded by a bursar at the
    desk. Cash is confirmed on the spot — the money is already in hand, with
    nothing to reconcile; a cheque or bank slip starts pending until
    `confirm_manual_payment` checks it against the bank statement."""
    if method not in {PaymentMethod.CASH, PaymentMethod.CHEQUE, PaymentMethod.BANK_SLIP}:
        raise InvalidPaymentMethod("Use initiate_mobile_payment for mobile money.")

    invoice = Invoice.objects.select_related().get(pk=invoice_id)
    payment = Payment(
        invoice=invoice,
        method=method,
        amount=amount,
        currency=invoice.currency,
        reference=reference,
        received_by=actor if getattr(actor, "pk", None) else None,
        notes=notes,
    )
    payment.audit_reason = f"{method} payment recorded"
    payment.full_clean()
    payment.save()

    if method == PaymentMethod.CASH:
        _confirm_payment(payment)
    return payment


@transaction.atomic
def confirm_manual_payment(payment: Payment, *, actor: Any) -> Payment:
    if payment.status != PaymentStatus.PENDING:
        raise DomainError(f"This payment is already {payment.status}.", code="not_pending")
    _confirm_payment(payment)
    return payment


@transaction.atomic
def reject_manual_payment(payment: Payment, *, actor: Any, reason: str) -> Payment:
    if not reason.strip():
        raise ReasonRequired("A reason is required to reject a payment.")
    if payment.status != PaymentStatus.PENDING:
        raise DomainError(f"This payment is already {payment.status}.", code="not_pending")
    payment.status = PaymentStatus.FAILED
    payment.notes = f"{payment.notes}\nRejected: {reason}".strip()
    payment.audit_reason = f"Payment rejected: {reason}"
    payment.full_clean()
    payment.save()
    return payment


@transaction.atomic
def initiate_mobile_payment(
    *, invoice_id: int, payer_ref: str, actor: Any, amount: Decimal | None = None
) -> Payment:
    invoice = Invoice.objects.get(pk=invoice_id)
    requested = amount if amount is not None else invoice_balance(invoice)
    if requested <= 0:
        raise DomainError("This invoice has nothing outstanding.", code="nothing_due")

    provider = get_payment_provider()
    intent = provider.initiate(requested, invoice.currency, payer_ref, invoice.invoice_number)

    payment = Payment(
        invoice=invoice,
        method=PaymentMethod.MOBILE_MONEY,
        amount=requested,
        currency=invoice.currency,
        provider=intent.provider,
        reference=intent.reference,
        status=PaymentStatus.PENDING,
    )
    payment.audit_reason = "Mobile money payment initiated"
    payment.full_clean()
    payment.save()
    return payment


@transaction.atomic
def poll_mobile_payment(payment: Payment) -> Payment:
    """Checks a pending mobile-money payment against the provider's own
    record of it — never against anything the client claims."""
    if payment.status != PaymentStatus.PENDING:
        return payment
    provider = get_payment_provider()
    result = provider.status(payment.reference)
    if result.state == PaymentState.CONFIRMED:
        _confirm_payment(payment, paid_at=result.paid_at)
    elif result.state in {PaymentState.FAILED, PaymentState.CANCELLED}:
        payment.status = result.state
        payment.audit_reason = f"Provider reports {result.state}: {result.detail}"
        payment.full_clean()
        payment.save()
    return payment


@transaction.atomic
def handle_payment_webhook(request: Any) -> Payment | None:
    """FR-FIN-03. A payment is only ever confirmed on the provider's own,
    signature-verified word — never from an unverified callback body."""
    provider = get_payment_provider()
    event = provider.verify_callback(request)
    if not event.verified or event.state != PaymentState.CONFIRMED:
        return None

    payment = Payment.objects.filter(
        reference=event.reference, status=PaymentStatus.PENDING
    ).first()
    if payment is None:
        return None
    _confirm_payment(payment, paid_at=event.value_date)
    return payment


def _confirm_payment(payment: Payment, *, paid_at: datetime | date | None = None) -> None:
    semester = payment.invoice.semester
    payment.status = PaymentStatus.CONFIRMED
    payment.confirmed_at = paid_at if isinstance(paid_at, datetime) else timezone.now()
    payment.receipt_number = generate_receipt_number(
        calendar.academic_year_name(semester.academic_year_id)
    )
    payment.audit_reason = f"Payment confirmed; receipt {payment.receipt_number}"
    payment.full_clean()
    payment.save()
    _refresh_invoice_status(payment.invoice)


# --------------------------------------------------------------- scholarships


@transaction.atomic
def create_scholarship(
    *,
    student_id: int,
    academic_year_id: int,
    coverage_type: str,
    sponsor_id: int | None = None,
    percentage: Decimal | None = None,
    fixed_amount: Decimal | None = None,
    currency: str | None = None,
    notes: str = "",
    actor: Any = None,
) -> Scholarship:
    scholarship = Scholarship(
        student_id=student_id,
        academic_year_id=academic_year_id,
        sponsor_id=sponsor_id,
        coverage_type=coverage_type,
        percentage=percentage,
        fixed_amount=fixed_amount,
        currency=currency or academics_config.base_currency(),
        notes=notes,
    )
    scholarship.audit_reason = "Scholarship recorded"
    scholarship.full_clean()
    scholarship.save()
    return scholarship


@transaction.atomic
def update_scholarship(
    scholarship: Scholarship,
    *,
    percentage: Decimal | None = None,
    fixed_amount: Decimal | None = None,
    is_active: bool | None = None,
    actor: Any = None,
) -> Scholarship:
    if percentage is not None:
        scholarship.percentage = percentage
    if fixed_amount is not None:
        scholarship.fixed_amount = fixed_amount
    if is_active is not None:
        scholarship.is_active = is_active
    scholarship.audit_reason = "Scholarship updated"
    scholarship.full_clean()
    scholarship.save()
    return scholarship


# -------------------------------------------------------------------- refunds


@transaction.atomic
def request_refund(*, payment_id: int, amount: Decimal, reason: str, actor: Any) -> Refund:
    if not reason.strip():
        raise ReasonRequired("A reason is required to request a refund.")
    payment = Payment.objects.get(pk=payment_id)
    if payment.status != PaymentStatus.CONFIRMED:
        raise PaymentNotConfirmed()

    already_claimed = payment.refunds.exclude(status=RefundStatus.REJECTED).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0")
    if amount > payment.amount - already_claimed:
        raise RefundExceedsPayment("This would refund more than was paid.")

    refund = Refund(
        payment=payment,
        amount=amount,
        currency=payment.currency,
        reason=reason,
        requested_by=actor if getattr(actor, "pk", None) else None,
    )
    refund.audit_reason = "Refund requested"
    refund.full_clean()
    refund.save()
    return refund


@transaction.atomic
def decide_refund(refund: Refund, *, approve: bool, actor: Any, notes: str) -> Refund:
    if not notes.strip():
        raise ReasonRequired("A reason is required to decide a refund.")
    if refund.status != RefundStatus.REQUESTED:
        raise InvalidRefundTransition(f"This refund is already {refund.status}.")

    refund.status = RefundStatus.APPROVED if approve else RefundStatus.REJECTED
    refund.decided_by = actor
    refund.decision_notes = notes
    refund.decided_at = timezone.now()
    refund.audit_reason = f"Refund {refund.status}: {notes}"
    refund.full_clean()
    refund.save()
    return refund


@transaction.atomic
def mark_refund_paid(refund: Refund, *, actor: Any) -> Refund:
    if refund.status != RefundStatus.APPROVED:
        raise InvalidRefundTransition("Only an approved refund can be marked paid.")
    refund.status = RefundStatus.PAID
    refund.paid_at = timezone.now()
    refund.audit_reason = "Refund paid out"
    refund.full_clean()
    refund.save()
    return refund


# --------------------------------------------------------------- holds & reports


def fee_balance_for_student(student_id: int) -> Decimal:
    """Total outstanding across every unpaid or partially-paid invoice — what
    `FeeBalanceHoldProvider` checks before letting a student register."""
    invoices = Invoice.objects.filter(
        student_id=student_id,
        status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID],
    )
    return sum((invoice_balance(invoice) for invoice in invoices), Decimal("0"))


def revenue_summary(*, academic_year_id: int | None = None) -> dict[str, Any]:
    """FR-RPT-01's "revenue" — invoiced, collected and outstanding, computed
    from the same `Invoice`/`Payment` rows `defaulter_report` and
    `invoice_balance` already trust, not a second ledger that could
    disagree with them."""
    invoices = Invoice.objects.all()
    if academic_year_id is not None:
        invoices = invoices.filter(semester__academic_year_id=academic_year_id)

    total_invoiced = invoices.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    total_discount = invoices.aggregate(total=Sum("discount_amount"))["total"] or Decimal("0")
    net_billed = total_invoiced - total_discount
    outstanding = sum(
        (
            invoice_balance(invoice)
            for invoice in invoices.filter(
                status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID]
            )
        ),
        Decimal("0"),
    )
    return {
        "total_invoiced": total_invoiced,
        "total_discount": total_discount,
        "net_billed": net_billed,
        "collected": net_billed - outstanding,
        "outstanding": outstanding,
    }


def defaulter_report(*, semester_id: int | None = None) -> list[dict[str, Any]]:
    """FR-FIN-07. One row per invoice still carrying a balance."""
    queryset = Invoice.objects.filter(
        status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID]
    ).select_related("student", "semester")
    if semester_id is not None:
        queryset = queryset.filter(semester_id=semester_id)

    today = timezone.localdate()
    rows = []
    for invoice in queryset:
        balance = invoice_balance(invoice)
        if balance <= 0:
            continue
        rows.append(
            {
                "invoice_id": invoice.pk,
                "invoice_number": invoice.invoice_number,
                "student_id": invoice.student_id,
                "student_number": invoice.student.student_id,
                "student_name": invoice.student.get_full_name(),
                "semester_id": invoice.semester_id,
                "balance": balance,
                "currency": invoice.currency,
                "due_date": invoice.due_date,
                "days_overdue": max(0, (today - invoice.due_date).days),
            }
        )
    return rows
