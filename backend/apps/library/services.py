"""Library services (FR-LIB-01…03)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.library.models import LibraryItem, Loan, LoanStatus

DEFAULT_LOAN_PERIOD_DAYS = 14


class NoCopiesAvailable(DomainError):
    code = "no_copies_available"
    status_code = 409


class ExactlyOneBorrowerRequired(DomainError):
    code = "exactly_one_borrower_required"


class ReasonRequired(DomainError):
    code = "reason_required"


@transaction.atomic
def create_library_item(*, actor: Any = None, **fields: Any) -> LibraryItem:
    item = LibraryItem(**fields)
    item.audit_reason = "Catalogued"
    item.full_clean()
    item.save()
    return item


@transaction.atomic
def update_library_item(item: LibraryItem, *, actor: Any = None, **fields: Any) -> LibraryItem:
    for name, value in fields.items():
        setattr(item, name, value)
    item.audit_reason = "Catalogue entry updated"
    item.full_clean()
    item.save()
    return item


def _policy_defaults() -> tuple[int, Decimal, str]:
    from apps.academics.services import config as academics_config
    from apps.library.models import LibraryPolicy

    policy = LibraryPolicy.get()
    if policy is None:
        return DEFAULT_LOAN_PERIOD_DAYS, Decimal("0"), academics_config.base_currency()
    return policy.loan_period_days, policy.daily_fine_rate, policy.currency


@transaction.atomic
def checkout_item(
    *,
    item_id: int,
    borrower_student_id: int | None = None,
    borrower_staff_id: int | None = None,
    due_date: date | None = None,
    actor: Any = None,
) -> Loan:
    if bool(borrower_student_id) == bool(borrower_staff_id):
        raise ExactlyOneBorrowerRequired()

    from apps.library.models import LibraryItem

    item = LibraryItem.objects.select_for_update().get(pk=item_id)
    if item.available_copies <= 0:
        raise NoCopiesAvailable("Every copy of this item is currently on loan.")

    loan_period_days, _rate, currency = _policy_defaults()
    loan = Loan(
        item=item,
        borrower_student_id=borrower_student_id,
        borrower_staff_id=borrower_staff_id,
        due_date=due_date or (timezone.localdate() + timedelta(days=loan_period_days)),
        currency=currency,
    )
    loan.audit_reason = "Item checked out"
    loan.full_clean()
    loan.save()
    return loan


@transaction.atomic
def return_item(loan: Loan, *, actor: Any = None, returned_at: datetime | None = None) -> Loan:
    if loan.status != LoanStatus.ACTIVE:
        raise DomainError(f"This loan is already {loan.status}.", code="not_active")

    when = returned_at or timezone.now()
    days_overdue = max(0, (when.date() - loan.due_date).days)
    _period, daily_rate, _currency = _policy_defaults()

    loan.status = LoanStatus.RETURNED
    loan.returned_at = when
    loan.fine_amount = daily_rate * days_overdue
    loan.audit_reason = (
        f"Returned {days_overdue} day(s) late; fine {loan.fine_amount}"
        if days_overdue
        else "Returned on time"
    )
    loan.full_clean()
    loan.save()
    return loan


@transaction.atomic
def mark_lost(loan: Loan, *, actor: Any = None) -> Loan:
    if loan.status != LoanStatus.ACTIVE:
        raise DomainError(f"This loan is already {loan.status}.", code="not_active")
    loan.status = LoanStatus.LOST
    loan.audit_reason = "Reported lost"
    loan.full_clean()
    loan.save()
    return loan


@transaction.atomic
def waive_fine(loan: Loan, *, actor: Any, reason: str) -> Loan:
    if not reason.strip():
        raise ReasonRequired("A reason is required to waive a fine.")
    loan.fine_waived = True
    loan.waived_by = actor
    loan.waived_reason = reason
    loan.audit_reason = f"Fine waived: {reason}"
    loan.full_clean()
    loan.save()
    return loan


def outstanding_fines_for_student(student_id: int) -> Decimal:
    total = Decimal("0")
    for loan in Loan.objects.filter(borrower_student_id=student_id, fine_waived=False):
        total += loan.owed
    return total
