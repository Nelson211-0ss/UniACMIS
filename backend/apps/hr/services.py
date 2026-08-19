"""HR services (FR-HR-01…04)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.hr.models import Appraisal, Contract, LeaveRequest, LeaveStatus


class ReasonRequired(DomainError):
    code = "reason_required"


class InvalidLeaveTransition(DomainError):
    code = "invalid_leave_transition"
    status_code = 409


@transaction.atomic
def create_contract(
    *,
    staff_id: int,
    contract_type: str,
    position: str,
    start_date: date,
    basic_salary: Decimal,
    end_date: date | None = None,
    currency: str | None = None,
    actor: Any = None,
) -> Contract:
    from apps.academics.services import config as academics_config

    contract = Contract(
        staff_id=staff_id,
        contract_type=contract_type,
        position=position,
        start_date=start_date,
        end_date=end_date,
        basic_salary=basic_salary,
        currency=currency or academics_config.base_currency(),
    )
    contract.audit_reason = "Contract created"
    contract.full_clean()
    contract.save()
    return contract


@transaction.atomic
def end_contract(contract: Contract, *, end_date: date, actor: Any = None) -> Contract:
    contract.end_date = end_date
    contract.is_active = False
    contract.audit_reason = "Contract ended"
    contract.full_clean()
    contract.save()
    return contract


@transaction.atomic
def submit_leave_request(
    *, staff_id: int, leave_type: str, start_date: date, end_date: date, reason: str, actor: Any
) -> LeaveRequest:
    if not reason.strip():
        raise ReasonRequired("A reason is required to request leave.")
    request = LeaveRequest(
        staff_id=staff_id,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
    )
    request.audit_reason = "Leave requested"
    request.full_clean()
    request.save()
    return request


@transaction.atomic
def endorse_leave_request(request: LeaveRequest, *, actor: Any) -> LeaveRequest:
    if request.status != LeaveStatus.SUBMITTED:
        raise InvalidLeaveTransition(f"Cannot endorse a request that is {request.status}.")
    request.status = LeaveStatus.ENDORSED
    request.endorsed_by = actor
    request.endorsed_at = timezone.now()
    request.audit_reason = "Endorsed by supervisor"
    request.full_clean()
    request.save()
    return request


@transaction.atomic
def decide_leave_request(
    request: LeaveRequest, *, approve: bool, actor: Any, notes: str
) -> LeaveRequest:
    if not notes.strip():
        raise ReasonRequired("A reason is required to decide a leave request.")
    if request.status != LeaveStatus.ENDORSED:
        raise InvalidLeaveTransition("Only an endorsed request may receive HR's final decision.")
    request.status = LeaveStatus.APPROVED if approve else LeaveStatus.REJECTED
    request.decided_by = actor
    request.decision_notes = notes
    request.decided_at = timezone.now()
    request.audit_reason = f"Leave {request.status}: {notes}"
    request.full_clean()
    request.save()
    return request


@transaction.atomic
def record_appraisal(
    *,
    staff_id: int,
    academic_year_id: int,
    rating: int,
    reviewer: Any,
    comments: str = "",
    promotion_recommended: bool = False,
    actor: Any = None,
) -> Appraisal:
    appraisal = Appraisal(
        staff_id=staff_id,
        academic_year_id=academic_year_id,
        reviewer=reviewer,
        rating=rating,
        comments=comments,
        promotion_recommended=promotion_recommended,
    )
    appraisal.audit_reason = "Appraisal recorded"
    appraisal.full_clean()
    appraisal.save()
    return appraisal


@transaction.atomic
def update_appraisal(
    appraisal: Appraisal,
    *,
    rating: int | None = None,
    comments: str | None = None,
    promotion_recommended: bool | None = None,
    actor: Any = None,
) -> Appraisal:
    if rating is not None:
        appraisal.rating = rating
    if comments is not None:
        appraisal.comments = comments
    if promotion_recommended is not None:
        appraisal.promotion_recommended = promotion_recommended
    appraisal.audit_reason = "Appraisal updated"
    appraisal.full_clean()
    appraisal.save()
    return appraisal


def payroll_export() -> list[dict[str, Any]]:
    """FR-HR-04. The figures a real payroll system needs — never a computed
    net pay, which is explicitly out of scope."""
    contracts = Contract.objects.filter(is_active=True).select_related("staff", "staff__user")
    return [
        {
            "staff_id": contract.staff_id,
            "staff_number": contract.staff.staff_number,
            "staff_name": contract.staff.user.get_full_name(),
            "position": contract.position,
            "contract_type": contract.contract_type,
            "basic_salary": contract.basic_salary,
            "currency": contract.currency,
        }
        for contract in contracts
    ]
