"""Hostel service layer (FR-HOS-01…03): room inventory, allocation and the
fee link to finance."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.core.choices import Gender, SouthSudanState
from apps.hostel import services
from apps.hostel.models import AllocationStatus, HostelPolicy
from apps.registry.models import Gender as RegistryGender
from apps.registry.services import create_student

pytestmark = pytest.mark.django_db


@pytest.fixture
def room():
    return services.create_room(
        building="Hall A", room_number="101", capacity=2, gender_restriction=Gender.FEMALE
    )


@pytest.fixture
def mens_room():
    return services.create_room(
        building="Hall B", room_number="101", capacity=1, gender_restriction=Gender.MALE
    )


# -------------------------------------------------------------------- rooms


def test_creating_a_room(room):
    assert room.pk is not None
    assert room.available_beds == 2


def test_updating_a_room(room):
    updated = services.update_room(room, capacity=4)
    assert updated.capacity == 4


# --------------------------------------------------------------- allocation


def test_allocating_a_room_to_a_matching_student(room, student, academic_year):
    allocation = services.allocate_room(
        student_id=student.pk, room_id=room.pk, academic_year_id=academic_year.pk
    )
    assert allocation.status == AllocationStatus.ACTIVE
    room.refresh_from_db()
    assert room.available_beds == 1


def test_allocating_across_a_gender_mismatch_is_rejected(mens_room, student, academic_year):
    with pytest.raises(services.GenderMismatch):
        services.allocate_room(
            student_id=student.pk, room_id=mens_room.pk, academic_year_id=academic_year.pk
        )


def test_a_full_room_cannot_take_another_allocation(
    mens_room, programme, curriculum_version, academic_year
):
    first = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Peter",
        last_name="Garang",
        gender=RegistryGender.MALE,
        curriculum_version_id=curriculum_version.pk,
        reason="test",
    )
    second = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="John",
        last_name="Wani",
        gender=RegistryGender.MALE,
        curriculum_version_id=curriculum_version.pk,
        reason="test",
    )
    services.allocate_room(
        student_id=first.pk, room_id=mens_room.pk, academic_year_id=academic_year.pk
    )
    with pytest.raises(services.RoomFull):
        services.allocate_room(
            student_id=second.pk, room_id=mens_room.pk, academic_year_id=academic_year.pk
        )


def test_a_student_cannot_hold_two_active_allocations(room, student, academic_year):
    other_room = services.create_room(
        building="Hall A", room_number="102", capacity=2, gender_restriction=Gender.FEMALE
    )
    services.allocate_room(
        student_id=student.pk, room_id=room.pk, academic_year_id=academic_year.pk
    )
    with pytest.raises(services.AlreadyAllocated):
        services.allocate_room(
            student_id=student.pk, room_id=other_room.pk, academic_year_id=academic_year.pk
        )


def test_vacating_frees_the_bed(room, student, academic_year):
    allocation = services.allocate_room(
        student_id=student.pk, room_id=room.pk, academic_year_id=academic_year.pk
    )
    vacated = services.vacate_allocation(allocation, reason="Graduated")
    assert vacated.status == AllocationStatus.VACATED
    assert vacated.vacated_at is not None
    room.refresh_from_db()
    assert room.available_beds == 2


def test_vacating_an_already_vacated_allocation_is_rejected(room, student, academic_year):
    allocation = services.allocate_room(
        student_id=student.pk, room_id=room.pk, academic_year_id=academic_year.pk
    )
    services.vacate_allocation(allocation)
    from apps.core.exceptions import DomainError

    with pytest.raises(DomainError):
        services.vacate_allocation(allocation)


def test_a_room_edited_to_mismatch_its_occupant_fails_validation(room, student, academic_year):
    services.allocate_room(
        student_id=student.pk, room_id=room.pk, academic_year_id=academic_year.pk
    )
    with pytest.raises(ValidationError):
        services.update_room(room, gender_restriction=Gender.MALE)


# ---------------------------------------------------------------- priority


def test_waiting_list_priority_favours_disability_then_state_then_entry_year(
    programme, curriculum_version, academic_year
):
    plain = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Plain",
        last_name="Case",
        gender=RegistryGender.FEMALE,
        curriculum_version_id=curriculum_version.pk,
        reason="test",
    )
    disabled = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Needs",
        last_name="Support",
        gender=RegistryGender.FEMALE,
        curriculum_version_id=curriculum_version.pk,
        has_disability=True,
        disability_details="Wheelchair user",
        reason="test",
    )
    outside = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Far",
        last_name="FromHome",
        gender=RegistryGender.FEMALE,
        curriculum_version_id=curriculum_version.pk,
        state_of_origin=SouthSudanState.OUTSIDE_SOUTH_SUDAN,
        reason="test",
    )

    ranked = services.waiting_list_priority([plain.pk, disabled.pk, outside.pk])
    assert ranked[0] == disabled.pk
    assert ranked[1] == outside.pk
    assert ranked[2] == plain.pk


# --------------------------------------------------------------- finance link


def test_fee_for_active_allocation_is_zero_without_one(student, academic_year):
    assert services.fee_for_active_allocation(
        student_id=student.pk, academic_year_id=academic_year.pk
    ) == Decimal("0")


def test_fee_for_active_allocation_reflects_the_policy(room, student, academic_year):
    HostelPolicy.objects.create(termly_fee=Decimal("50000.00"), currency="SSP")
    services.allocate_room(
        student_id=student.pk, room_id=room.pk, academic_year_id=academic_year.pk
    )

    fee = services.fee_for_active_allocation(
        student_id=student.pk, academic_year_id=academic_year.pk
    )
    assert fee == Decimal("50000.00")
