"""
Payment providers.

`MockPaymentProvider` lets the finance flows in Phase 4 be built and tested
before mobile-money credentials exist (SRS §8 open item 2). The real MTN Mobile
Money and Zain Cash / M-Gurush implementations plug in behind the same interface.

Two rules any real implementation must honour, encoded here so they are not
rediscovered later:

1. `verify_callback` must verify the provider's signature. An unverified callback
   returns `verified=False` and must never move a fee balance — an unauthenticated
   "payment confirmed" webhook is free tuition.
2. `reference` is the provider's own identifier and must be stored, so a payment
   can be reconciled against the provider's statement (FR-FIN-03).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.core.ports import PaymentEvent, PaymentIntent, PaymentState, PaymentStatusResult


class MockPaymentProvider:
    """In-memory sandbox. Confirms on the second `status()` poll, so callers must
    handle the pending state rather than assuming instant settlement."""

    name = "mock"

    def __init__(self) -> None:
        self._intents: dict[str, dict[str, Any]] = {}

    def initiate(
        self, amount: Decimal, currency: str, payer_ref: str, invoice_ref: str
    ) -> PaymentIntent:
        reference = f"MOCK-{uuid.uuid4().hex[:12].upper()}"
        self._intents[reference] = {
            "amount": Decimal(str(amount)),
            "currency": currency,
            "payer_ref": payer_ref,
            "invoice_ref": invoice_ref,
            "state": PaymentState.PENDING,
            "polls": 0,
            "paid_at": None,
        }
        return PaymentIntent(
            provider=self.name,
            reference=reference,
            state=PaymentState.PENDING,
            amount=Decimal(str(amount)),
            currency=currency,
            instructions=f"Sandbox intent {reference}: approve by polling status twice.",
        )

    def status(self, reference: str) -> PaymentStatusResult:
        intent = self._intents.get(reference)
        if intent is None:
            return PaymentStatusResult(
                reference=reference, state=PaymentState.FAILED, detail="Unknown reference."
            )

        intent["polls"] += 1
        if intent["polls"] >= 2 and intent["state"] == PaymentState.PENDING:
            intent["state"] = PaymentState.CONFIRMED
            intent["paid_at"] = timezone.now()

        return PaymentStatusResult(
            reference=reference,
            state=intent["state"],
            amount=intent["amount"],
            currency=intent["currency"],
            paid_at=intent["paid_at"],
        )

    def verify_callback(self, request: Any) -> PaymentEvent:
        """Sandbox: accepts a JSON body carrying `reference`, and only marks the
        event verified when a shared-secret header matches."""
        data = getattr(request, "data", {}) or {}
        reference = str(data.get("reference", ""))
        secret = request.headers.get("X-Mock-Signature", "") if hasattr(request, "headers") else ""
        intent = self._intents.get(reference)

        verified = bool(reference) and secret == "sandbox"
        if verified and intent is not None:
            intent["state"] = PaymentState.CONFIRMED
            intent["paid_at"] = timezone.now()

        return PaymentEvent(
            provider=self.name,
            reference=reference,
            state=intent["state"] if intent else PaymentState.FAILED,
            amount=intent["amount"] if intent else None,
            currency=intent["currency"] if intent else None,
            verified=verified,
            raw=dict(data),
            value_date=timezone.localdate() if verified else None,
        )

    # Test seam: lets a test force a confirmed payment without polling.
    def force_confirm(self, reference: str, when: datetime | None = None) -> None:
        if reference in self._intents:
            self._intents[reference]["state"] = PaymentState.CONFIRMED
            self._intents[reference]["paid_at"] = when or timezone.now()
