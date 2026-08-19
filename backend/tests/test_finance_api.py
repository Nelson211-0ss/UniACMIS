"""
Finance API: fee structures and scholarships are finance's to manage; a
student sees only their own invoices, payments and refund requests; only
finance may confirm a payment or decide a refund (FR-FIN-01…08).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.finance import services
from apps.finance.models import PaymentMethod, Residency

pytestmark = pytest.mark.django_db

FEE_STRUCTURES_URL = "/api/v1/finance/fee-structures/"
INVOICES_URL = "/api/v1/finance/invoices/"
PAYMENTS_URL = "/api/v1/finance/payments/"
REFUNDS_URL = "/api/v1/finance/refunds/"
DEFAULTERS_URL = "/api/v1/finance/reports/defaulters/"
WEBHOOK_URL = "/api/v1/finance/webhooks/payment/"


@pytest.fixture
def fee_structure(programme, academic_year):
    return services.create_fee_structure(
        programme_id=programme.pk,
        academic_year_id=academic_year.pk,
        level=1,
        residency=Residency.LOCAL,
        amount=Decimal("500000.00"),
    )


@pytest.fixture
def invoice(fee_structure, student, semester, registrar):
    return services.generate_invoice(
        student_id=student.pk, semester_id=semester.pk, actor=registrar
    )


@pytest.fixture
def student_portal_user(roles, user_factory, student):
    user = user_factory(role="student", email="student-portal-finance@test.ss")
    student.user = user
    student.save(update_fields=["user"])
    return user


@pytest.mark.integration
def test_finance_can_create_a_fee_structure(finance_officer, as_user, programme, academic_year):
    response = as_user(finance_officer).post(
        FEE_STRUCTURES_URL,
        {
            "programme": programme.pk,
            "academic_year": academic_year.pk,
            "level": 1,
            "residency": Residency.LOCAL,
            "amount": "500000.00",
        },
        format="json",
    )
    assert response.status_code == 201


@pytest.mark.integration
def test_a_registrar_cannot_create_a_fee_structure(registrar, as_user, programme, academic_year):
    response = as_user(registrar).post(
        FEE_STRUCTURES_URL,
        {
            "programme": programme.pk,
            "academic_year": academic_year.pk,
            "level": 1,
            "residency": Residency.LOCAL,
            "amount": "500000.00",
        },
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_finance_can_generate_an_invoice(
    finance_officer, as_user, fee_structure, student, semester
):
    response = as_user(finance_officer).post(
        f"{INVOICES_URL}generate/", {"student": student.pk, "semester": semester.pk}, format="json"
    )
    assert response.status_code == 201
    assert response.data["amount"] == "500000.00"


@pytest.mark.integration
def test_a_student_only_sees_their_own_invoice(
    student_portal_user, as_user, invoice, fee_structure, programme, academic_year, registrar
):
    from apps.registry.models import Gender
    from apps.registry.services import create_student

    other_student = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Other",
        last_name="Payer",
        gender=Gender.FEMALE,
        curriculum_version_id=None,
        reason="test",
    )
    services.generate_invoice(
        student_id=other_student.pk, semester_id=invoice.semester_id, actor=registrar
    )

    response = as_user(student_portal_user).get(INVOICES_URL)
    assert response.status_code == 200
    student_ids = {row["student"] for row in response.data["results"]}
    assert student_ids == {invoice.student_id}


@pytest.mark.integration
def test_finance_can_record_and_confirm_a_bank_slip(finance_officer, as_user, invoice):
    record = as_user(finance_officer).post(
        f"{PAYMENTS_URL}record/",
        {
            "invoice": invoice.pk,
            "method": PaymentMethod.BANK_SLIP,
            "amount": str(invoice.net_amount),
            "reference": "SLIP-API-0001",
        },
        format="json",
    )
    assert record.status_code == 201
    assert record.data["status"] == "pending"

    confirm = as_user(finance_officer).post(f"{PAYMENTS_URL}{record.data['id']}/confirm/")
    assert confirm.status_code == 200
    assert confirm.data["status"] == "confirmed"
    assert confirm.data["receipt_number"]


@pytest.mark.integration
def test_a_student_cannot_record_a_payment(student_portal_user, as_user, invoice):
    response = as_user(student_portal_user).post(
        f"{PAYMENTS_URL}record/",
        {
            "invoice": invoice.pk,
            "method": PaymentMethod.CASH,
            "amount": str(invoice.net_amount),
            "reference": "SLIP-API-0002",
        },
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_a_student_can_request_a_refund_but_not_decide_it(
    student_portal_user, as_user, invoice, finance_officer
):
    payment = services.record_manual_payment(
        invoice_id=invoice.pk,
        method=PaymentMethod.CASH,
        amount=Decimal("100000.00"),
        reference="CASH-API-0001",
        actor=finance_officer,
    )

    request_response = as_user(student_portal_user).post(
        REFUNDS_URL,
        {"payment": payment.pk, "amount": "50000.00", "reason": "Dropped a course"},
        format="json",
    )
    assert request_response.status_code == 201
    # The response reflects the full record (status, decision fields), not
    # just the narrow write shape — the create-response bug fixed in earlier
    # phases, checked again here since Refund uses the same mixin.
    assert request_response.data["status"] == "requested"
    refund_id = request_response.data["id"]

    denied = as_user(student_portal_user).post(
        f"{REFUNDS_URL}{refund_id}/decide/",
        {"approve": True, "notes": "Self-approving"},
        format="json",
    )
    assert denied.status_code == 403


@pytest.mark.integration
def test_finance_can_decide_a_refund(as_user, finance_officer, invoice):
    payment = services.record_manual_payment(
        invoice_id=invoice.pk,
        method=PaymentMethod.CASH,
        amount=Decimal("100000.00"),
        reference="CASH-API-0002",
        actor=finance_officer,
    )
    refund = services.request_refund(
        payment_id=payment.pk, amount=Decimal("50000.00"), reason="test", actor=None
    )
    response = as_user(finance_officer).post(
        f"{REFUNDS_URL}{refund.pk}/decide/", {"approve": True, "notes": "Verified"}, format="json"
    )
    assert response.status_code == 200
    assert response.data["status"] == "approved"


@pytest.mark.integration
def test_finance_can_view_the_defaulter_report(finance_officer, as_user, invoice):
    response = as_user(finance_officer).get(DEFAULTERS_URL)
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["invoice_number"] == invoice.invoice_number


@pytest.mark.integration
def test_a_lecturer_cannot_view_the_defaulter_report(lecturer, as_user):
    response = as_user(lecturer).get(DEFAULTERS_URL)
    assert response.status_code == 403


@pytest.mark.integration
def test_the_webhook_endpoint_is_public_but_requires_a_valid_signature(api, invoice):
    payment = services.initiate_mobile_payment(
        invoice_id=invoice.pk, payer_ref="0955000000", actor=None
    )

    unsigned = api.post(WEBHOOK_URL, {"reference": payment.reference}, format="json")
    assert unsigned.status_code == 200
    assert unsigned.data["payment_id"] is None  # not verified, so nothing changed

    payment.refresh_from_db()
    assert payment.status == "pending"

    signed = api.post(
        WEBHOOK_URL,
        {"reference": payment.reference},
        format="json",
        HTTP_X_MOCK_SIGNATURE="sandbox",
    )
    assert signed.status_code == 200
    assert signed.data["payment_id"] == payment.pk
    payment.refresh_from_db()
    assert payment.status == "confirmed"
    assert payment.receipt_number
