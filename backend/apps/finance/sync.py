"""
Offline sync handler for manual payment capture (FR-FIN-03).

A cash or bank-slip payment recorded at a campus bursar's desk during an
outage is exactly the case `ConflictPolicy.FLAG_FOR_REVIEW` exists for (see
`CLAUDE.md`): two different amounts queued against the same reference are two
people's record of what was paid, and picking one silently destroys evidence
of the other. `apply()` checks for a divergent stored value itself, the same
shape as `examinations.sync.MarkHandler`.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError

from apps.core.exceptions import SyncConflictDetected
from apps.core.models import ConflictPolicy
from apps.core.sync.handlers import SyncOperationInput, register_handler
from apps.finance import services
from apps.finance.models import Payment, PaymentMethod

REQUIRED_FIELDS = ("invoice_id", "method", "amount", "reference")
MANUAL_METHODS = {PaymentMethod.CASH, PaymentMethod.CHEQUE, PaymentMethod.BANK_SLIP}


@register_handler
class ManualPaymentHandler:
    entity = "finance.payment"
    actions = ("create",)
    conflict_policy = ConflictPolicy.FLAG_FOR_REVIEW
    required_permission = "finance.add_payment"

    def apply(self, op: SyncOperationInput, actor: Any) -> dict[str, Any]:
        payload = op.payload or {}
        missing = [f for f in REQUIRED_FIELDS if payload.get(f) in (None, "")]
        if missing:
            raise ValidationError(dict.fromkeys(missing, "This field is required."))

        method = payload["method"]
        if method not in MANUAL_METHODS:
            raise ValidationError({"method": "Must be cash, cheque or a bank slip."})

        try:
            amount = Decimal(str(payload["amount"]))
        except InvalidOperation as exc:
            raise ValidationError({"amount": "Must be a number."}) from exc

        reference = payload["reference"]
        existing = Payment.objects.filter(reference=reference).first()
        if existing is not None and (existing.amount != amount or existing.method != method):
            raise SyncConflictDetected(
                field_name="amount",
                server_value=f"{existing.amount} ({existing.method})",
                client_value=f"{amount} ({method})",
                server_updated_at=existing.updated_at,
                target=existing,
                message=(
                    f"A payment of {existing.amount} is already recorded against "
                    f"reference {reference}; held for review rather than overwritten."
                ),
            )
        if existing is not None:
            return {"id": existing.pk, "status": existing.status, "_target": existing}

        payment = services.record_manual_payment(
            invoice_id=int(payload["invoice_id"]),
            method=method,
            amount=amount,
            reference=reference,
            actor=actor,
            notes=payload.get("notes", ""),
        )
        return {"id": payment.pk, "status": payment.status, "_target": payment}
