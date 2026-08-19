"""
Offline sync handler for attendance capture (FR-ATT-01).

Reference implementation: `apps/registry/sync.py`. One operation per student per
session, so a device that queued a register for forty students lands the
thirty-nine good rows even if one student's registration has since changed.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from django.core.exceptions import ValidationError

from apps.attendance import services
from apps.core.models import ConflictPolicy
from apps.core.sync.handlers import SyncOperationInput, register_handler

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("timetable_entry_id", "session_date", "registration_id", "status")


@register_handler
class SessionRecordHandler:
    """Creates or corrects one student's mark for one dated session."""

    entity = "attendance.sessionrecord"
    actions = ("create", "update")
    # A register corrected after a paper-and-outage sitting is a normal
    # occurrence, not two sources of truth in dispute — unlike a mark
    # (FR-EXM-01), nothing downstream has acted on the earlier value by the
    # time a device reconnects, so overwriting it (with the audit trail
    # recording what changed) is safe here where it would not be for a grade.
    conflict_policy = ConflictPolicy.LAST_WRITE_WINS
    required_permission = "attendance.add_sessionrecord"

    def apply(self, op: SyncOperationInput, actor: Any) -> dict[str, Any]:
        payload = op.payload or {}
        missing = [f for f in REQUIRED_FIELDS if payload.get(f) in (None, "")]
        if missing:
            raise ValidationError(dict.fromkeys(missing, "This field is required."))

        session_date = payload["session_date"]
        if isinstance(session_date, str):
            session_date = date.fromisoformat(session_date)

        records = services.record_session(
            timetable_entry_id=int(payload["timetable_entry_id"]),
            session_date=session_date,
            marks=[
                {
                    "registration_id": int(payload["registration_id"]),
                    "status": payload["status"],
                    "notes": payload.get("notes", ""),
                }
            ],
            actor=actor,
        )
        record = records[0]
        return {"id": record.pk, "status": record.status, "_target": record}
