"""
Offline sync handler for CA score entry (FR-EXM-01).

Unlike attendance, a mark is exactly the case `ConflictPolicy.FLAG_FOR_REVIEW`
exists for (see `CLAUDE.md`): two different scores queued for the same
(registration, assessment) are two people's honest belief about what a
student earned, and silently picking one destroys the evidence of the other.
`apply()` therefore checks for a divergent stored value itself — the engine's
`LAST_WRITE_WINS` auto-overwrite-with-audit path never runs for this handler.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError

from apps.core.exceptions import SyncConflictDetected
from apps.core.models import ConflictPolicy
from apps.core.sync.handlers import SyncOperationInput, register_handler
from apps.examinations import services
from apps.examinations.models import Mark

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("registration_id", "assessment_id", "score")


@register_handler
class MarkHandler:
    entity = "examinations.mark"
    actions = ("create", "update")
    conflict_policy = ConflictPolicy.FLAG_FOR_REVIEW
    required_permission = "examinations.add_mark"

    def apply(self, op: SyncOperationInput, actor: Any) -> dict[str, Any]:
        payload = op.payload or {}
        missing = [f for f in REQUIRED_FIELDS if payload.get(f) in (None, "")]
        if missing:
            raise ValidationError(dict.fromkeys(missing, "This field is required."))

        registration_id = int(payload["registration_id"])
        assessment_id = int(payload["assessment_id"])
        try:
            score = Decimal(str(payload["score"]))
        except InvalidOperation as exc:
            raise ValidationError({"score": "Must be a number."}) from exc

        existing = Mark.objects.filter(
            registration_id=registration_id, assessment_id=assessment_id
        ).first()
        if existing is not None and existing.score != score:
            raise SyncConflictDetected(
                field_name="score",
                server_value=existing.score,
                client_value=score,
                server_updated_at=existing.updated_at,
                target=existing,
                message=(
                    f"A score of {existing.score} is already recorded for this mark; "
                    f"held for review rather than overwritten with {score}."
                ),
            )

        mark = services.record_mark(
            registration_id=registration_id,
            assessment_id=assessment_id,
            score=score,
            actor=actor,
        )
        return {"id": mark.pk, "score": str(mark.score), "_target": mark}
