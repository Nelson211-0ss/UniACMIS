"""Hostel API: room inventory is hostel-staff territory; a student sees only
their own allocation; allocating/vacating are separately permissioned
actions (FR-HOS-01…03)."""

from __future__ import annotations

import pytest

from apps.core.choices import Gender

pytestmark = pytest.mark.django_db

ROOMS_URL = "/api/v1/hostel/rooms/"
ALLOCATIONS_URL = "/api/v1/hostel/allocations/"


@pytest.fixture
def room(hostel_officer, as_user):
    response = as_user(hostel_officer).post(
        ROOMS_URL,
        {
            "building": "Hall A",
            "room_number": "101",
            "capacity": 2,
            "gender_restriction": Gender.FEMALE,
        },
        format="json",
    )
    assert response.status_code == 201
    return response.data


@pytest.mark.integration
def test_hostel_staff_can_create_a_room(hostel_officer, as_user):
    response = as_user(hostel_officer).post(
        ROOMS_URL,
        {
            "building": "Hall C",
            "room_number": "201",
            "capacity": 3,
            "gender_restriction": Gender.MALE,
        },
        format="json",
    )
    assert response.status_code == 201


@pytest.mark.integration
def test_a_lecturer_cannot_create_a_room(lecturer, as_user):
    response = as_user(lecturer).post(
        ROOMS_URL,
        {
            "building": "Hall C",
            "room_number": "201",
            "capacity": 3,
            "gender_restriction": Gender.MALE,
        },
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_hostel_staff_can_allocate_a_room(hostel_officer, as_user, room, student, academic_year):
    response = as_user(hostel_officer).post(
        f"{ALLOCATIONS_URL}allocate/",
        {"student": student.pk, "room": room["id"], "academic_year": academic_year.pk},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["status"] == "active"


@pytest.mark.integration
def test_a_gender_mismatched_allocation_is_rejected(
    hostel_officer, as_user, room, academic_year, programme, curriculum_version
):
    from apps.registry.models import Gender as RegistryGender
    from apps.registry.services import create_student

    male_student = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Peter",
        last_name="Garang",
        gender=RegistryGender.MALE,
        curriculum_version_id=curriculum_version.pk,
        reason="test",
    )
    response = as_user(hostel_officer).post(
        f"{ALLOCATIONS_URL}allocate/",
        {"student": male_student.pk, "room": room["id"], "academic_year": academic_year.pk},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.integration
def test_a_lecturer_cannot_allocate_a_room(lecturer, as_user, room, student, academic_year):
    response = as_user(lecturer).post(
        f"{ALLOCATIONS_URL}allocate/",
        {"student": student.pk, "room": room["id"], "academic_year": academic_year.pk},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_a_student_only_sees_their_own_allocation(
    hostel_officer, as_user, room, student, academic_year, student_portal_user
):
    as_user(hostel_officer).post(
        f"{ALLOCATIONS_URL}allocate/",
        {"student": student.pk, "room": room["id"], "academic_year": academic_year.pk},
        format="json",
    )

    response = as_user(student_portal_user).get(ALLOCATIONS_URL)
    assert response.status_code == 200
    assert {row["student"] for row in response.data["results"]} == {student.pk}


@pytest.mark.integration
def test_vacating_a_room(hostel_officer, as_user, room, student, academic_year):
    allocated = as_user(hostel_officer).post(
        f"{ALLOCATIONS_URL}allocate/",
        {"student": student.pk, "room": room["id"], "academic_year": academic_year.pk},
        format="json",
    )
    allocation_id = allocated.data["id"]

    response = as_user(hostel_officer).post(
        f"{ALLOCATIONS_URL}{allocation_id}/vacate/", {"reason": "Withdrew"}, format="json"
    )
    assert response.status_code == 200
    assert response.data["status"] == "vacated"


@pytest.mark.integration
def test_a_student_cannot_vacate_their_own_allocation(
    hostel_officer, as_user, room, student, academic_year, student_portal_user
):
    allocated = as_user(hostel_officer).post(
        f"{ALLOCATIONS_URL}allocate/",
        {"student": student.pk, "room": room["id"], "academic_year": academic_year.pk},
        format="json",
    )
    allocation_id = allocated.data["id"]

    response = as_user(student_portal_user).post(f"{ALLOCATIONS_URL}{allocation_id}/vacate/")
    assert response.status_code == 403


@pytest.mark.integration
def test_generating_an_invoice_includes_the_hostel_fee(
    hostel_officer, as_user, room, student, academic_year, semester, programme, registrar
):
    from decimal import Decimal

    from apps.finance import services as finance_services
    from apps.finance.models import Residency
    from apps.hostel.models import HostelPolicy

    HostelPolicy.objects.create(termly_fee=Decimal("50000.00"), currency="SSP")
    finance_services.create_fee_structure(
        programme_id=programme.pk,
        academic_year_id=academic_year.pk,
        level=1,
        residency=Residency.LOCAL,
        amount=Decimal("500000.00"),
    )
    as_user(hostel_officer).post(
        f"{ALLOCATIONS_URL}allocate/",
        {"student": student.pk, "room": room["id"], "academic_year": academic_year.pk},
        format="json",
    )

    invoice = finance_services.generate_invoice(
        student_id=student.pk, semester_id=semester.pk, actor=registrar
    )
    assert invoice.amount == Decimal("550000.00")
