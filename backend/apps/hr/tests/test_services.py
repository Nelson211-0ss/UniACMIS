"""HR service layer (FR-HR-01…04): contracts, leave's two-level approval,
appraisal and the payroll export."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.hr import services
from apps.hr.models import ContractType, LeaveStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(roles, staff_factory):
    return staff_factory("lecturer").staff_profile


# ------------------------------------------------------------------ contracts


def test_creating_a_permanent_contract_needs_no_end_date(staff):
    contract = services.create_contract(
        staff_id=staff.pk,
        contract_type=ContractType.PERMANENT,
        position="Lecturer II",
        start_date=date(2026, 1, 1),
        basic_salary=Decimal("2500.00"),
    )
    assert contract.pk is not None
    assert contract.end_date is None
    assert contract.currency  # defaulted from institution config


def test_a_fixed_term_contract_requires_an_end_date(staff):
    with pytest.raises(ValidationError):
        services.create_contract(
            staff_id=staff.pk,
            contract_type=ContractType.FIXED_TERM,
            position="Visiting Lecturer",
            start_date=date(2026, 1, 1),
            basic_salary=Decimal("1500.00"),
        )


def test_end_date_must_be_after_start_date(staff):
    with pytest.raises(ValidationError):
        services.create_contract(
            staff_id=staff.pk,
            contract_type=ContractType.FIXED_TERM,
            position="Visiting Lecturer",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 1, 1),
            basic_salary=Decimal("1500.00"),
        )


def test_ending_a_contract(staff):
    contract = services.create_contract(
        staff_id=staff.pk,
        contract_type=ContractType.PERMANENT,
        position="Lecturer II",
        start_date=date(2026, 1, 1),
        basic_salary=Decimal("2500.00"),
    )
    ended = services.end_contract(contract, end_date=date(2026, 12, 31))
    assert ended.is_active is False
    assert ended.end_date == date(2026, 12, 31)


# --------------------------------------------------------------------- leave


def test_submitting_a_leave_request(staff):
    request = services.submit_leave_request(
        staff_id=staff.pk,
        leave_type="annual",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 10),
        reason="Annual leave",
        actor=staff.user,
    )
    assert request.status == LeaveStatus.SUBMITTED


def test_submitting_leave_without_a_reason_is_rejected(staff):
    with pytest.raises(services.ReasonRequired):
        services.submit_leave_request(
            staff_id=staff.pk,
            leave_type="annual",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 10),
            reason="   ",
            actor=staff.user,
        )


def test_end_date_before_start_date_is_rejected(staff):
    with pytest.raises(ValidationError):
        services.submit_leave_request(
            staff_id=staff.pk,
            leave_type="annual",
            start_date=date(2026, 9, 10),
            end_date=date(2026, 9, 1),
            reason="Annual leave",
            actor=staff.user,
        )


@pytest.fixture
def leave_request(staff):
    return services.submit_leave_request(
        staff_id=staff.pk,
        leave_type="sick",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 3),
        reason="Unwell",
        actor=staff.user,
    )


def test_endorsing_a_leave_request(leave_request, hod):
    endorsed = services.endorse_leave_request(leave_request, actor=hod)
    assert endorsed.status == LeaveStatus.ENDORSED
    assert endorsed.endorsed_by == hod
    assert endorsed.endorsed_at is not None


def test_cannot_endorse_an_already_endorsed_request(leave_request, hod):
    services.endorse_leave_request(leave_request, actor=hod)
    with pytest.raises(services.InvalidLeaveTransition):
        services.endorse_leave_request(leave_request, actor=hod)


def test_deciding_before_endorsement_is_rejected(leave_request, hr_officer):
    with pytest.raises(services.InvalidLeaveTransition):
        services.decide_leave_request(
            leave_request, approve=True, actor=hr_officer, notes="Approved"
        )


def test_deciding_requires_notes(leave_request, hod, hr_officer):
    services.endorse_leave_request(leave_request, actor=hod)
    with pytest.raises(services.ReasonRequired):
        services.decide_leave_request(leave_request, approve=True, actor=hr_officer, notes=" ")


def test_deciding_approves_a_leave_request(leave_request, hod, hr_officer):
    services.endorse_leave_request(leave_request, actor=hod)
    decided = services.decide_leave_request(
        leave_request, approve=True, actor=hr_officer, notes="Approved by HR"
    )
    assert decided.status == LeaveStatus.APPROVED
    assert decided.decided_by == hr_officer
    assert decided.decided_at is not None


def test_deciding_rejects_a_leave_request(leave_request, hod, hr_officer):
    services.endorse_leave_request(leave_request, actor=hod)
    decided = services.decide_leave_request(
        leave_request, approve=False, actor=hr_officer, notes="Insufficient balance"
    )
    assert decided.status == LeaveStatus.REJECTED


# ----------------------------------------------------------------- appraisal


def test_recording_an_appraisal(staff, academic_year, hod):
    appraisal = services.record_appraisal(
        staff_id=staff.pk,
        academic_year_id=academic_year.pk,
        rating=4,
        reviewer=hod,
        comments="Strong year",
        promotion_recommended=True,
    )
    assert appraisal.pk is not None
    assert appraisal.promotion_recommended is True


def test_rating_must_be_between_one_and_five(staff, academic_year, hod):
    with pytest.raises(ValidationError):
        services.record_appraisal(
            staff_id=staff.pk, academic_year_id=academic_year.pk, rating=6, reviewer=hod
        )


def test_only_one_appraisal_per_staff_per_year(staff, academic_year, hod):
    services.record_appraisal(
        staff_id=staff.pk, academic_year_id=academic_year.pk, rating=3, reviewer=hod
    )
    with pytest.raises(ValidationError):
        services.record_appraisal(
            staff_id=staff.pk, academic_year_id=academic_year.pk, rating=4, reviewer=hod
        )


def test_updating_an_appraisal(staff, academic_year, hod):
    appraisal = services.record_appraisal(
        staff_id=staff.pk, academic_year_id=academic_year.pk, rating=3, reviewer=hod
    )
    updated = services.update_appraisal(appraisal, rating=5, promotion_recommended=True)
    assert updated.rating == 5
    assert updated.promotion_recommended is True


# ------------------------------------------------------------------- payroll


def test_payroll_export_lists_only_active_contracts(staff):
    services.create_contract(
        staff_id=staff.pk,
        contract_type=ContractType.PERMANENT,
        position="Lecturer II",
        start_date=date(2026, 1, 1),
        basic_salary=Decimal("2500.00"),
    )
    stale = services.create_contract(
        staff_id=staff.pk,
        contract_type=ContractType.FIXED_TERM,
        position="Locum",
        start_date=date(2020, 1, 1),
        end_date=date(2020, 6, 1),
        basic_salary=Decimal("500.00"),
    )
    services.end_contract(stale, end_date=date(2020, 6, 1))

    rows = services.payroll_export()
    assert any(row["position"] == "Lecturer II" for row in rows)
    assert all(row["position"] != "Locum" for row in rows)
