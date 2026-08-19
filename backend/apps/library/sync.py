"""
Offline sync handler for circulation (FR-LIB-03) — reference implementation:
`apps/registry/sync.py`. A checkout is a physical event, not a financial one
(the fine, if any, is computed later at return), so `LAST_WRITE_WINS` is the
right policy, the same reasoning `attendance.sync` gives.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

from apps.core.models import ConflictPolicy
from apps.core.sync.handlers import SyncOperationInput, register_handler
from apps.library import services

REQUIRED_FIELDS = ("item_id",)


@register_handler
class LoanCheckoutHandler:
    entity = "library.loan"
    actions = ("create",)
    conflict_policy = ConflictPolicy.LAST_WRITE_WINS
    required_permission = "library.add_loan"

    def apply(self, op: SyncOperationInput, actor: Any) -> dict[str, Any]:
        payload = op.payload or {}
        missing = [f for f in REQUIRED_FIELDS if payload.get(f) in (None, "")]
        if missing:
            raise ValidationError(dict.fromkeys(missing, "This field is required."))

        borrower_student_id = payload.get("borrower_student_id")
        borrower_staff_id = payload.get("borrower_staff_id")
        loan = services.checkout_item(
            item_id=int(payload["item_id"]),
            borrower_student_id=int(borrower_student_id) if borrower_student_id else None,
            borrower_staff_id=int(borrower_staff_id) if borrower_staff_id else None,
            actor=actor,
        )
        return {"id": loan.pk, "due_date": str(loan.due_date), "_target": loan}
