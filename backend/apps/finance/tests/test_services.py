"""
Finance service layer (FR-FIN-01…08): fee structures, invoicing against
them, manual and mobile-money payments, scholarships, refunds and the
defaulter report.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.core.exceptions import BlockedByHold, ConfigurationError
from apps.enrollment.services import register_course
from apps.finance import services
from apps.finance.models import (
    CoverageType,
    InvoiceStatus,
    PaymentMethod,
    PaymentStatus,
    RefundStatus,
    Residency,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def fee_structure(programme, academic_year):
    return services.create_fee_structure(
        programme_id=programme.pk,
        academic_year_id=academic_year.pk,
        level=1,
        residency=Residency.LOCAL,
        amount=Decimal("500000.00"),
        currency="SSP",
    )


@pytest.fixture
def invoice(fee_structure, student, semester, registrar):
    return services.generate_invoice(
        student_id=student.pk, semester_id=semester.pk, actor=registrar
    )


# ---------------------------------------------------------------- fee structures


def test_creating_a_fee_structure(programme, academic_year):
    structure = services.create_fee_structure(
        programme_id=programme.pk,
        academic_year_id=academic_year.pk,
        level=1,
        residency=Residency.LOCAL,
        amount=Decimal("500000.00"),
    )
    assert structure.pk is not None
    assert structure.currency == "SSP"


def test_a_duplicate_fee_structure_is_rejected(fee_structure, programme, academic_year):
    with pytest.raises(ValidationError):
        services.create_fee_structure(
            programme_id=programme.pk,
            academic_year_id=academic_year.pk,
            level=1,
            residency=Residency.LOCAL,
            amount=Decimal("1.00"),
        )


# ------------------------------------------------------------------------ invoices


def test_generating_an_invoice(fee_structure, student, semester, registrar):
    invoice = services.generate_invoice(
        student_id=student.pk, semester_id=semester.pk, actor=registrar
    )
    assert invoice.amount == Decimal("500000.00")
    assert invoice.discount_amount == Decimal("0.00")
    assert invoice.status == InvoiceStatus.ISSUED
    assert invoice.invoice_number.startswith("INV/")


def test_generating_a_second_invoice_for_the_same_semester_is_rejected(
    invoice, student, semester, registrar
):
    with pytest.raises(services.DuplicateInvoice):
        services.generate_invoice(student_id=student.pk, semester_id=semester.pk, actor=registrar)


def test_generating_an_invoice_with_no_fee_structure_configured(student, semester, registrar):
    with pytest.raises(ConfigurationError):
        services.generate_invoice(student_id=student.pk, semester_id=semester.pk, actor=registrar)


def test_an_active_scholarship_discounts_the_invoice(
    fee_structure, student, semester, academic_year, registrar
):
    services.create_scholarship(
        student_id=student.pk,
        academic_year_id=academic_year.pk,
        coverage_type=CoverageType.PERCENTAGE,
        percentage=Decimal("50"),
    )
    invoice = services.generate_invoice(
        student_id=student.pk, semester_id=semester.pk, actor=registrar
    )
    assert invoice.discount_amount == Decimal("250000.00")
    assert invoice.net_amount == Decimal("250000.00")


def test_generate_invoices_for_semester_skips_students_already_invoiced(
    fee_structure, student, course, semester, registrar
):
    register_course(
        student_id=student.pk, course_id=course.pk, semester_id=semester.pk, actor=registrar
    )
    services.generate_invoice(student_id=student.pk, semester_id=semester.pk, actor=registrar)

    result = services.generate_invoices_for_semester(semester_id=semester.pk, actor=registrar)
    assert result["created"] == 0
    assert result["skipped"] == [{"student_id": student.pk, "reason": "duplicate_invoice"}]


def test_generate_invoices_for_semester_creates_for_a_newly_registered_student(
    fee_structure, student, course, semester, registrar
):
    register_course(
        student_id=student.pk, course_id=course.pk, semester_id=semester.pk, actor=registrar
    )
    result = services.generate_invoices_for_semester(semester_id=semester.pk, actor=registrar)
    assert result["created"] == 1
    assert result["skipped"] == []


# ------------------------------------------------------------------------ payments


def test_cash_payment_is_confirmed_immediately(invoice, finance_officer):
    payment = services.record_manual_payment(
        invoice_id=invoice.pk,
        method=PaymentMethod.CASH,
        amount=invoice.net_amount,
        reference="CASH-0001",
        actor=finance_officer,
    )
    assert payment.status == PaymentStatus.CONFIRMED
    assert payment.receipt_number.startswith("RCT/")
    invoice.refresh_from_db()
    assert invoice.status == InvoiceStatus.PAID


def test_a_partial_cash_payment_leaves_the_invoice_partially_paid(invoice, finance_officer):
    services.record_manual_payment(
        invoice_id=invoice.pk,
        method=PaymentMethod.CASH,
        amount=Decimal("100000.00"),
        reference="CASH-0002",
        actor=finance_officer,
    )
    invoice.refresh_from_db()
    assert invoice.status == InvoiceStatus.PARTIALLY_PAID
    assert services.invoice_balance(invoice) == Decimal("400000.00")


def test_a_bank_slip_starts_pending_and_confirm_settles_it(invoice, finance_officer):
    payment = services.record_manual_payment(
        invoice_id=invoice.pk,
        method=PaymentMethod.BANK_SLIP,
        amount=invoice.net_amount,
        reference="SLIP-0001",
        actor=finance_officer,
    )
    assert payment.status == PaymentStatus.PENDING
    invoice.refresh_from_db()
    assert invoice.status == InvoiceStatus.ISSUED

    confirmed = services.confirm_manual_payment(payment, actor=finance_officer)
    assert confirmed.status == PaymentStatus.CONFIRMED
    assert confirmed.receipt_number
    invoice.refresh_from_db()
    assert invoice.status == InvoiceStatus.PAID


def test_rejecting_a_pending_payment_requires_a_reason(invoice, finance_officer):
    payment = services.record_manual_payment(
        invoice_id=invoice.pk,
        method=PaymentMethod.BANK_SLIP,
        amount=invoice.net_amount,
        reference="SLIP-0002",
        actor=finance_officer,
    )
    with pytest.raises(services.ReasonRequired):
        services.reject_manual_payment(payment, actor=finance_officer, reason="   ")

    rejected = services.reject_manual_payment(
        payment, actor=finance_officer, reason="Slip does not match statement"
    )
    assert rejected.status == PaymentStatus.FAILED


def test_mobile_money_payment_confirms_on_the_second_poll(invoice, settings):
    settings.PAYMENT_PROVIDER = "apps.core.providers.payments.MockPaymentProvider"
    from apps.core.providers import reset_provider_cache

    reset_provider_cache()

    payment = services.initiate_mobile_payment(
        invoice_id=invoice.pk, payer_ref="0955000000", actor=None
    )
    assert payment.status == PaymentStatus.PENDING
    assert payment.provider == "mock"

    services.poll_mobile_payment(payment)
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.PENDING  # first poll: still pending

    services.poll_mobile_payment(payment)
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.CONFIRMED
    assert payment.receipt_number


def test_manual_payment_method_cannot_be_mobile_money(invoice, finance_officer):
    with pytest.raises(services.InvalidPaymentMethod):
        services.record_manual_payment(
            invoice_id=invoice.pk,
            method=PaymentMethod.MOBILE_MONEY,
            amount=invoice.net_amount,
            reference="X",
            actor=finance_officer,
        )


# --------------------------------------------------------------------- scholarships


def test_a_fixed_amount_scholarship_caps_at_the_invoice_amount(
    fee_structure, student, semester, academic_year, registrar
):
    services.create_scholarship(
        student_id=student.pk,
        academic_year_id=academic_year.pk,
        coverage_type=CoverageType.FIXED_AMOUNT,
        fixed_amount=Decimal("999999999.00"),
    )
    invoice = services.generate_invoice(
        student_id=student.pk, semester_id=semester.pk, actor=registrar
    )
    assert invoice.discount_amount == invoice.amount
    assert invoice.net_amount == Decimal("0.00")


def test_percentage_coverage_requires_a_percentage(student, academic_year):
    with pytest.raises(ValidationError):
        services.create_scholarship(
            student_id=student.pk,
            academic_year_id=academic_year.pk,
            coverage_type=CoverageType.PERCENTAGE,
        )


# -------------------------------------------------------------------------- refunds


def test_requesting_a_refund_on_an_unconfirmed_payment_is_rejected(invoice, finance_officer):
    payment = services.record_manual_payment(
        invoice_id=invoice.pk,
        method=PaymentMethod.BANK_SLIP,
        amount=invoice.net_amount,
        reference="SLIP-0003",
        actor=finance_officer,
    )
    with pytest.raises(services.PaymentNotConfirmed):
        services.request_refund(
            payment_id=payment.pk, amount=Decimal("10"), reason="test", actor=None
        )


def test_a_refund_cannot_exceed_the_payment(invoice, finance_officer):
    payment = services.record_manual_payment(
        invoice_id=invoice.pk,
        method=PaymentMethod.CASH,
        amount=Decimal("100000.00"),
        reference="CASH-0003",
        actor=finance_officer,
    )
    with pytest.raises(services.RefundExceedsPayment):
        services.request_refund(
            payment_id=payment.pk, amount=Decimal("200000.00"), reason="Overpaid", actor=None
        )


def test_the_full_refund_workflow(invoice, finance_officer):
    payment = services.record_manual_payment(
        invoice_id=invoice.pk,
        method=PaymentMethod.CASH,
        amount=Decimal("100000.00"),
        reference="CASH-0004",
        actor=finance_officer,
    )
    refund = services.request_refund(
        payment_id=payment.pk, amount=Decimal("50000.00"), reason="Dropped a course", actor=None
    )
    assert refund.status == RefundStatus.REQUESTED

    with pytest.raises(services.ReasonRequired):
        services.decide_refund(refund, approve=True, actor=finance_officer, notes="")

    approved = services.decide_refund(
        refund, approve=True, actor=finance_officer, notes="Confirmed against the drop record"
    )
    assert approved.status == RefundStatus.APPROVED

    with pytest.raises(services.InvalidRefundTransition):
        services.decide_refund(refund, approve=True, actor=finance_officer, notes="again")

    paid = services.mark_refund_paid(refund, actor=finance_officer)
    assert paid.status == RefundStatus.PAID
    assert paid.paid_at is not None


def test_a_rejected_refund_can_be_requested_again_up_to_the_full_amount(invoice, finance_officer):
    payment = services.record_manual_payment(
        invoice_id=invoice.pk,
        method=PaymentMethod.CASH,
        amount=Decimal("100000.00"),
        reference="CASH-0005",
        actor=finance_officer,
    )
    first = services.request_refund(
        payment_id=payment.pk, amount=Decimal("100000.00"), reason="test", actor=None
    )
    services.decide_refund(first, approve=False, actor=finance_officer, notes="Not eligible")

    # A rejected refund does not count against the payment's remaining balance.
    second = services.request_refund(
        payment_id=payment.pk, amount=Decimal("100000.00"), reason="test", actor=None
    )
    assert second.pk != first.pk


# ------------------------------------------------------------- holds & defaulters


def test_fee_balance_for_student_sums_outstanding_invoices(invoice):
    assert services.fee_balance_for_student(invoice.student_id) == invoice.net_amount


def test_a_paid_invoice_does_not_count_toward_the_balance(invoice, finance_officer):
    services.record_manual_payment(
        invoice_id=invoice.pk,
        method=PaymentMethod.CASH,
        amount=invoice.net_amount,
        reference="CASH-0006",
        actor=finance_officer,
    )
    assert services.fee_balance_for_student(invoice.student_id) == Decimal("0")


@pytest.mark.integration
def test_the_real_hold_provider_blocks_registration_for_an_unpaid_balance(
    invoice, course, semester, registrar
):
    with pytest.raises(BlockedByHold):
        register_course(
            student_id=invoice.student_id, course_id=course.pk, semester_id=semester.pk, actor=None
        )


def test_defaulter_report_lists_unpaid_invoices(invoice):
    report = services.defaulter_report()
    assert len(report) == 1
    assert report[0]["invoice_number"] == invoice.invoice_number
    assert report[0]["balance"] == invoice.net_amount


def test_defaulter_report_excludes_paid_invoices(invoice, finance_officer):
    services.record_manual_payment(
        invoice_id=invoice.pk,
        method=PaymentMethod.CASH,
        amount=invoice.net_amount,
        reference="CASH-0007",
        actor=finance_officer,
    )
    assert services.defaulter_report() == []
