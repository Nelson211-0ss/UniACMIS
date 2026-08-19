"""Hostel services (FR-HOS-01…03)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.hostel.models import Allocation, AllocationStatus, HostelPolicy, Room


class RoomFull(DomainError):
    code = "room_full"
    status_code = 409


class GenderMismatch(DomainError):
    code = "gender_mismatch"


class AlreadyAllocated(DomainError):
    code = "already_allocated"
    status_code = 409


class ReasonRequired(DomainError):
    code = "reason_required"


@transaction.atomic
def create_room(*, actor: Any = None, **fields: Any) -> Room:
    room = Room(**fields)
    room.audit_reason = "Room added"
    room.full_clean()
    room.save()
    return room


@transaction.atomic
def update_room(room: Room, *, actor: Any = None, **fields: Any) -> Room:
    for name, value in fields.items():
        setattr(room, name, value)
    room.audit_reason = "Room updated"
    room.full_clean()
    room.save()
    return room


@transaction.atomic
def allocate_room(
    *, student_id: int, room_id: int, academic_year_id: int, actor: Any = None
) -> Allocation:
    from apps.registry.services import gender_for_student

    room = Room.objects.select_for_update().get(pk=room_id)
    if room.available_beds <= 0:
        raise RoomFull("This room has no free beds.")
    if gender_for_student(student_id) != room.gender_restriction:
        raise GenderMismatch("This room is restricted to a gender the student did not declare.")
    if Allocation.objects.filter(student_id=student_id, status=AllocationStatus.ACTIVE).exists():
        raise AlreadyAllocated("This student already holds an active room allocation.")

    allocation = Allocation(
        student_id=student_id,
        room=room,
        academic_year_id=academic_year_id,
        allocated_at=timezone.now(),
        allocated_by=actor if getattr(actor, "pk", None) else None,
    )
    allocation.audit_reason = "Room allocated"
    allocation.full_clean()
    allocation.save()
    return allocation


@transaction.atomic
def vacate_allocation(allocation: Allocation, *, actor: Any = None, reason: str = "") -> Allocation:
    if allocation.status != AllocationStatus.ACTIVE:
        raise DomainError(f"This allocation is already {allocation.status}.", code="not_active")
    allocation.status = AllocationStatus.VACATED
    allocation.vacated_at = timezone.now()
    allocation.vacated_by = actor if getattr(actor, "pk", None) else None
    if reason:
        allocation.notes = reason
    allocation.audit_reason = "Room vacated" + (f": {reason}" if reason else "")
    allocation.full_clean()
    allocation.save()
    return allocation


def waiting_list_priority(student_ids: list[int]) -> list[int]:
    """FR-HOS-02's "configurable priority rules", implemented as this
    documented ranking rather than a data-driven rules engine — the same
    "detection over generation" scope line Phase 3 drew for timetabling
    (`docs/TRACEABILITY.md` D-3/D-7): a deterministic, explainable order
    beats a rules engine nobody has actually asked to reconfigure yet.

    Priority, highest first: (1) a declared disability, (2) a state of
    origin outside South Sudan — the campus is the only accommodation
    option realistically available to them, (3) an earlier entry year — a
    continuing student who already depends on the hostel keeps their place
    over a fresher who has not yet needed one. An unrecorded state of
    origin is treated as neutral, not as "outside" — a data gap is not
    evidence of need.
    """
    from apps.core.choices import SouthSudanState
    from apps.registry.services import hostel_priority_profile

    profiles = {row["id"]: row for row in hostel_priority_profile(student_ids)}

    def _key(student_id: int) -> tuple:
        profile = profiles.get(student_id, {})
        return (
            0 if profile.get("has_disability") else 1,
            0 if profile.get("state_of_origin") == SouthSudanState.OUTSIDE_SOUTH_SUDAN else 1,
            profile.get("entry_academic_year_id") or 0,
        )

    return sorted(student_ids, key=_key)


def _policy_defaults() -> tuple[Decimal, str]:
    from apps.academics.services import config as academics_config

    policy = HostelPolicy.get()
    if policy is None:
        return Decimal("0"), academics_config.base_currency()
    return policy.termly_fee, policy.currency


def fee_for_active_allocation(*, student_id: int, academic_year_id: int) -> Decimal:
    """FR-HOS-03: the flat termly fee `finance.generate_invoice` adds onto a
    student's tuition invoice, if and only if they hold an active allocation
    for that academic year. Zero, not an error, when they hold none —
    living off-campus is the common case, not an exception."""
    has_allocation = Allocation.objects.filter(
        student_id=student_id, academic_year_id=academic_year_id, status=AllocationStatus.ACTIVE
    ).exists()
    if not has_allocation:
        return Decimal("0")
    fee, _currency = _policy_defaults()
    return fee
