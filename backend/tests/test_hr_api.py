"""HR API: contracts and appraisals are HR/HOD territory; any staff member
may request their own leave, but only their HOD endorses and only HR decides
(FR-HR-01…04)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db

CONTRACTS_URL = "/api/v1/hr/contracts/"
LEAVE_URL = "/api/v1/hr/leave-requests/"
APPRAISALS_URL = "/api/v1/hr/appraisals/"
PAYROLL_URL = "/api/v1/hr/payroll-export/"


@pytest.mark.integration
def test_hr_can_create_a_contract(hr_officer, as_user, lecturer):
    response = as_user(hr_officer).post(
        CONTRACTS_URL,
        {
            "staff": lecturer.staff_profile.pk,
            "contract_type": "permanent",
            "position": "Lecturer I",
            "start_date": "2026-01-01",
            "basic_salary": "2500.00",
        },
        format="json",
    )
    assert response.status_code == 201


@pytest.mark.integration
def test_a_lecturer_cannot_create_a_contract(lecturer, as_user):
    response = as_user(lecturer).post(
        CONTRACTS_URL,
        {
            "staff": lecturer.staff_profile.pk,
            "contract_type": "permanent",
            "position": "Lecturer I",
            "start_date": "2026-01-01",
            "basic_salary": "2500.00",
        },
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_a_staff_member_can_request_their_own_leave(lecturer, as_user):
    response = as_user(lecturer).post(
        f"{LEAVE_URL}submit/",
        {
            "staff": lecturer.staff_profile.pk,
            "leave_type": "annual",
            "start_date": "2026-09-01",
            "end_date": "2026-09-10",
            "reason": "Annual leave",
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["status"] == "submitted"


@pytest.mark.integration
def test_a_lecturer_only_sees_their_own_leave_requests(lecturer, hod, as_user):
    as_user(lecturer).post(
        f"{LEAVE_URL}submit/",
        {
            "staff": lecturer.staff_profile.pk,
            "leave_type": "annual",
            "start_date": "2026-09-01",
            "end_date": "2026-09-10",
            "reason": "Annual leave",
        },
        format="json",
    )
    as_user(hod).post(
        f"{LEAVE_URL}submit/",
        {
            "staff": hod.staff_profile.pk,
            "leave_type": "sick",
            "start_date": "2026-09-01",
            "end_date": "2026-09-02",
            "reason": "Unwell",
        },
        format="json",
    )

    response = as_user(lecturer).get(LEAVE_URL)
    assert response.status_code == 200
    assert {row["staff"] for row in response.data["results"]} == {lecturer.staff_profile.pk}


@pytest.mark.integration
def test_a_hod_sees_their_departments_leave_requests(lecturer, hod, as_user):
    as_user(lecturer).post(
        f"{LEAVE_URL}submit/",
        {
            "staff": lecturer.staff_profile.pk,
            "leave_type": "annual",
            "start_date": "2026-09-01",
            "end_date": "2026-09-10",
            "reason": "Annual leave",
        },
        format="json",
    )

    response = as_user(hod).get(LEAVE_URL)
    assert response.status_code == 200
    assert lecturer.staff_profile.pk in {row["staff"] for row in response.data["results"]}


@pytest.mark.integration
def test_only_a_hod_may_endorse_leave(lecturer, hod, hr_officer, as_user):
    submitted = as_user(lecturer).post(
        f"{LEAVE_URL}submit/",
        {
            "staff": lecturer.staff_profile.pk,
            "leave_type": "annual",
            "start_date": "2026-09-01",
            "end_date": "2026-09-10",
            "reason": "Annual leave",
        },
        format="json",
    )
    leave_id = submitted.data["id"]

    denied = as_user(hr_officer).post(f"{LEAVE_URL}{leave_id}/endorse/")
    assert denied.status_code == 403

    endorsed = as_user(hod).post(f"{LEAVE_URL}{leave_id}/endorse/")
    assert endorsed.status_code == 200
    assert endorsed.data["status"] == "endorsed"


@pytest.mark.integration
def test_the_hod_who_endorsed_cannot_also_give_hrs_final_decision(lecturer, hod, as_user):
    submitted = as_user(lecturer).post(
        f"{LEAVE_URL}submit/",
        {
            "staff": lecturer.staff_profile.pk,
            "leave_type": "annual",
            "start_date": "2026-09-01",
            "end_date": "2026-09-10",
            "reason": "Annual leave",
        },
        format="json",
    )
    leave_id = submitted.data["id"]
    as_user(hod).post(f"{LEAVE_URL}{leave_id}/endorse/")

    response = as_user(hod).post(
        f"{LEAVE_URL}{leave_id}/decide/",
        {"approve": True, "notes": "Self-approving"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_hr_gives_the_final_decision_after_endorsement(lecturer, hod, hr_officer, as_user):
    submitted = as_user(lecturer).post(
        f"{LEAVE_URL}submit/",
        {
            "staff": lecturer.staff_profile.pk,
            "leave_type": "annual",
            "start_date": "2026-09-01",
            "end_date": "2026-09-10",
            "reason": "Annual leave",
        },
        format="json",
    )
    leave_id = submitted.data["id"]
    as_user(hod).post(f"{LEAVE_URL}{leave_id}/endorse/")

    response = as_user(hr_officer).post(
        f"{LEAVE_URL}{leave_id}/decide/",
        {"approve": True, "notes": "Approved by HR"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["status"] == "approved"


@pytest.mark.integration
def test_a_hod_can_record_an_appraisal_for_their_department(hod, lecturer, academic_year, as_user):
    response = as_user(hod).post(
        APPRAISALS_URL,
        {"staff": lecturer.staff_profile.pk, "academic_year": academic_year.pk, "rating": 4},
        format="json",
    )
    assert response.status_code == 201


@pytest.mark.integration
def test_hr_cannot_record_an_appraisal(hr_officer, lecturer, academic_year, as_user):
    response = as_user(hr_officer).post(
        APPRAISALS_URL,
        {"staff": lecturer.staff_profile.pk, "academic_year": academic_year.pk, "rating": 4},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_hr_can_export_payroll(hr_officer, lecturer, as_user):
    from apps.hr import services
    from apps.hr.models import ContractType

    services.create_contract(
        staff_id=lecturer.staff_profile.pk,
        contract_type=ContractType.PERMANENT,
        position="Lecturer I",
        start_date=date(2026, 1, 1),
        basic_salary=Decimal("2500.00"),
    )

    response = as_user(hr_officer).get(PAYROLL_URL)
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["position"] == "Lecturer I"


@pytest.mark.integration
def test_a_lecturer_cannot_export_payroll(lecturer, as_user):
    response = as_user(lecturer).get(PAYROLL_URL)
    assert response.status_code == 403
