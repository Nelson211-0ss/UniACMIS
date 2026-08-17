"""
Offline sync handler for student creation (NFR-AVAIL-01).

The concrete case: a registry clerk works through a stack of paper admission forms
in an office where the power and the link both come and go. Typed records queue on
the device and land when the connection returns — once, even if the batch is
retried three times.

This is also the reference implementation for Phase 3. Attendance, grade entry and
library circulation register handlers of the same shape; none of them re-implements
idempotency, permissions or conflict handling.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import ValidationError

from apps.core.exceptions import SyncConflictDetected
from apps.core.models import ConflictPolicy
from apps.core.sync.handlers import SyncOperationInput, register_handler
from apps.registry import services
from apps.registry.models import Student

logger = logging.getLogger(__name__)

ALLOWED_FIELDS = frozenset(
    {
        "programme_id",
        "entry_academic_year_id",
        "curriculum_version_id",
        "first_name",
        "middle_name",
        "last_name",
        "date_of_birth",
        "gender",
        "national_id_number",
        "passport_number",
        "nationality",
        "state_of_origin",
        "county",
        "has_disability",
        "disability_details",
        "phone",
        "alternate_phone",
        "email",
        "physical_address",
        "previous_institution",
        "previous_qualification",
        "sponsorship_type",
        "sponsor_id",
        "current_level",
        "admitted_on",
        "student_id",
    }
)

REQUIRED_FIELDS = ("programme_id", "entry_academic_year_id", "first_name", "last_name", "gender")


@register_handler
class StudentCreateHandler:
    """Creates a student from a queued offline payload."""

    entity = "registry.student"
    actions = ("create",)
    # Creation cannot conflict with a concurrent edit — the record does not exist
    # yet, and the idempotency ledger already covers a replayed create. Duplicate
    # *people* are a different problem, handled below.
    conflict_policy = ConflictPolicy.LAST_WRITE_WINS
    required_permission = "registry.add_student"

    def apply(self, op: SyncOperationInput, actor: Any) -> dict[str, Any]:
        payload = {k: v for k, v in (op.payload or {}).items() if k in ALLOWED_FIELDS}

        missing = [f for f in REQUIRED_FIELDS if not payload.get(f)]
        if missing:
            raise ValidationError(dict.fromkeys(missing, "This field is required."))

        # A device that queued the same person twice under different operation ids
        # (the clerk typed the form again after the app appeared to lose it) would
        # otherwise create two records with two different student IDs. The national
        # ID is the only identifier available before we issue one of our own.
        national_id = (payload.get("national_id_number") or "").strip()
        if national_id:
            existing = Student.all_objects.filter(national_id_number=national_id).first()
            if existing is not None:
                raise SyncConflictDetected(
                    field_name="national_id_number",
                    server_value=f"{existing.student_id} ({existing.get_full_name()})",
                    client_value=f"{payload.get('first_name')} {payload.get('last_name')}",
                    target=existing,
                    message=(
                        f"A student with national ID {national_id} already exists as "
                        f"{existing.student_id}. Held for review rather than creating a "
                        "second record for the same person."
                    ),
                )

        student = services.create_student(
            programme_id=payload.pop("programme_id"),
            entry_academic_year_id=payload.pop("entry_academic_year_id"),
            first_name=payload.pop("first_name"),
            last_name=payload.pop("last_name"),
            gender=payload.pop("gender"),
            actor=actor,
            student_id=payload.pop("student_id", None),
            reason=(
                f"Created offline on device '{op.device_id or 'unknown'}' "
                f"and synced (op {op.client_op_id})."
            ),
            **payload,
        )

        return {
            "id": student.pk,
            "student_id": student.student_id,
            "full_name": student.get_full_name(),
            # The engine records this against the sync operation so the row can be
            # traced back to the device that produced it.
            "_target": student,
        }
