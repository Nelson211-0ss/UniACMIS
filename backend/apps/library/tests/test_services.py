"""Library service layer (FR-LIB-01…03): catalogue, checkout/return and fines."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.library import services
from apps.library.models import ItemType, LibraryPolicy, LoanStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def item():
    return services.create_library_item(
        title="Introduction to Structural Engineering",
        author="J. Doe",
        item_type=ItemType.BOOK,
        total_copies=1,
    )


@pytest.fixture
def borrowing_staff(roles, staff_factory):
    return staff_factory("lecturer").staff_profile


# --------------------------------------------------------------------- catalogue


def test_creating_a_library_item():
    item = services.create_library_item(
        title="Journal of African Studies", item_type=ItemType.JOURNAL, total_copies=3
    )
    assert item.pk is not None
    assert item.available_copies == 3


def test_an_electronic_item_requires_a_resource_url():
    with pytest.raises(ValidationError):
        services.create_library_item(title="E-book", item_type=ItemType.EBOOK, is_electronic=True)


def test_updating_a_library_item(item):
    updated = services.update_library_item(item, total_copies=5)
    assert updated.total_copies == 5


# --------------------------------------------------------------------- checkout


def test_checking_out_an_item_to_a_student(item, student):
    loan = services.checkout_item(item_id=item.pk, borrower_student_id=student.pk)
    assert loan.status == LoanStatus.ACTIVE
    assert loan.due_date == timezone.localdate() + timedelta(days=14)
    item.refresh_from_db()
    assert item.available_copies == 0


def test_checking_out_an_item_to_a_staff_member(item, borrowing_staff):
    loan = services.checkout_item(item_id=item.pk, borrower_staff_id=borrowing_staff.pk)
    assert loan.borrower_staff_id == borrowing_staff.pk


def test_checkout_requires_exactly_one_borrower(item, student, borrowing_staff):
    with pytest.raises(services.ExactlyOneBorrowerRequired):
        services.checkout_item(item_id=item.pk)
    with pytest.raises(services.ExactlyOneBorrowerRequired):
        services.checkout_item(
            item_id=item.pk, borrower_student_id=student.pk, borrower_staff_id=borrowing_staff.pk
        )


def test_no_copies_available_blocks_a_second_checkout(item, student, borrowing_staff):
    services.checkout_item(item_id=item.pk, borrower_student_id=student.pk)
    with pytest.raises(services.NoCopiesAvailable):
        services.checkout_item(item_id=item.pk, borrower_staff_id=borrowing_staff.pk)


def test_checkout_uses_the_configured_loan_period(item, student):
    LibraryPolicy.objects.create(loan_period_days=7, daily_fine_rate=Decimal("100"), currency="SSP")
    loan = services.checkout_item(item_id=item.pk, borrower_student_id=student.pk)
    assert loan.due_date == timezone.localdate() + timedelta(days=7)


# ---------------------------------------------------------------------- return


def test_returning_on_time_has_no_fine(item, student):
    loan = services.checkout_item(item_id=item.pk, borrower_student_id=student.pk)
    returned = services.return_item(loan, returned_at=timezone.now())
    assert returned.status == LoanStatus.RETURNED
    assert returned.fine_amount == Decimal("0")


def test_returning_late_charges_a_fine(item, student):
    LibraryPolicy.objects.create(loan_period_days=14, daily_fine_rate=Decimal("50"), currency="SSP")
    loan = services.checkout_item(item_id=item.pk, borrower_student_id=student.pk)
    late = timezone.now() + timedelta(days=17)
    returned = services.return_item(loan, returned_at=late)
    assert returned.fine_amount == Decimal("150")


def test_returning_a_second_time_is_rejected(item, student):
    loan = services.checkout_item(item_id=item.pk, borrower_student_id=student.pk)
    services.return_item(loan, returned_at=timezone.now())
    with pytest.raises(DomainError):
        services.return_item(loan, returned_at=timezone.now())


def test_marking_a_loan_lost(item, student):
    loan = services.checkout_item(item_id=item.pk, borrower_student_id=student.pk)
    lost = services.mark_lost(loan)
    assert lost.status == LoanStatus.LOST


def test_waiving_a_fine_requires_a_reason(item, student, librarian):
    LibraryPolicy.objects.create(loan_period_days=14, daily_fine_rate=Decimal("50"), currency="SSP")
    loan = services.checkout_item(item_id=item.pk, borrower_student_id=student.pk)
    late = timezone.now() + timedelta(days=15)
    returned = services.return_item(loan, returned_at=late)
    with pytest.raises(services.ReasonRequired):
        services.waive_fine(returned, actor=librarian, reason=" ")


def test_waiving_a_fine_zeroes_out_what_is_owed(item, student, librarian):
    LibraryPolicy.objects.create(loan_period_days=14, daily_fine_rate=Decimal("50"), currency="SSP")
    loan = services.checkout_item(item_id=item.pk, borrower_student_id=student.pk)
    late = timezone.now() + timedelta(days=15)
    returned = services.return_item(loan, returned_at=late)
    assert returned.owed == Decimal("50")

    waived = services.waive_fine(
        returned, actor=librarian, reason="Library outage, not the borrower's fault"
    )
    assert waived.fine_waived is True
    assert waived.owed == Decimal("0")


def test_outstanding_fines_for_student_excludes_waived_loans(item, student, librarian):
    LibraryPolicy.objects.create(loan_period_days=14, daily_fine_rate=Decimal("50"), currency="SSP")
    loan = services.checkout_item(item_id=item.pk, borrower_student_id=student.pk)
    late = timezone.now() + timedelta(days=15)
    returned = services.return_item(loan, returned_at=late)

    assert services.outstanding_fines_for_student(student.pk) == Decimal("50")

    services.waive_fine(returned, actor=librarian, reason="Waived")
    assert services.outstanding_fines_for_student(student.pk) == Decimal("0")
