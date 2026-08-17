"""
Ports: the interfaces `core` and the modules talk to each other through.

`core` is the lowest layer and must not import any domain app (enforced by an
import-linter contract). When it needs domain behaviour — writing an audit entry,
asking whether a student owes fees — it resolves a *port* that the owning app
registered at startup. That is what lets Phase 2's enrollment code call a fee
check that Phase 4 has not been written yet, and lets `finance` be extracted into
its own service later without touching its callers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from apps.core.services.registry import registry

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ audit port


@runtime_checkable
class AuditPort(Protocol):
    """Implemented by `apps.audit`, which registers itself at app-ready."""

    def record_change(
        self,
        *,
        instance: Any,
        field_name: str,
        old_value: Any,
        new_value: Any,
        action: str = "update",
        reason: str = "",
        actor: Any | None = None,
    ) -> None: ...

    def record_action(
        self,
        *,
        instance: Any | None,
        action: str,
        description: str = "",
        reason: str = "",
        actor: Any | None = None,
    ) -> None: ...


class _NullAuditPort:
    """Fallback used only if `apps.audit` is not installed.

    Loud on purpose: an unaudited grade or money change is a compliance failure
    (FR-RPT-04), not a missing nice-to-have.
    """

    def record_change(self, **kwargs: Any) -> None:
        logger.error("Audit port unavailable; change not recorded: %s", kwargs.get("field_name"))

    def record_action(self, **kwargs: Any) -> None:
        logger.error("Audit port unavailable; action not recorded: %s", kwargs.get("action"))


def audit() -> AuditPort:
    provider = registry.get(AuditPort)
    return provider if provider is not None else _NullAuditPort()


# ------------------------------------------------------------------ hold port


@dataclass(frozen=True)
class Hold:
    """A reason a student may not proceed (registration, exams, clearance).

    FR-ENR-03 (registration holds), FR-EXM-06 (results withheld) and FR-DOC-04
    (graduation clearance) are the same shape of question asked by different
    modules, so they share one port.
    """

    code: str
    message: str
    source: str
    blocking: bool = True
    details: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class HoldProvider(Protocol):
    """Registered by any module that can block a student: finance (unpaid fees),
    registry (missing documents), discipline, library, hostel."""

    source: str

    def holds_for(self, student_id: int) -> list[Hold]: ...


# --------------------------------------------------------- notification port


@dataclass(frozen=True)
class DeliveryReceipt:
    provider: str
    channel: str
    reference: str
    accepted: bool
    detail: str = ""


@runtime_checkable
class NotificationProvider(Protocol):
    """SMS is the primary channel, not a fallback: many students have a feature
    phone and no data (NFR-USE-03, FR-COM-01)."""

    name: str

    def send_sms(self, to: str, body: str, ref: str = "") -> DeliveryReceipt: ...

    def send_email(self, to: str, subject: str, body: str, ref: str = "") -> DeliveryReceipt: ...


# -------------------------------------------------------------- payment port


class PaymentState:
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class PaymentIntent:
    provider: str
    reference: str
    state: str
    amount: Decimal
    currency: str
    instructions: str = ""


@dataclass(frozen=True)
class PaymentStatusResult:
    reference: str
    state: str
    amount: Decimal | None = None
    currency: str | None = None
    paid_at: datetime | None = None
    detail: str = ""


@dataclass(frozen=True)
class PaymentEvent:
    """A verified provider callback. `verified` is False when the signature did
    not check out — an unverified callback must never move a fee balance."""

    provider: str
    reference: str
    state: str
    amount: Decimal | None
    currency: str | None
    verified: bool
    raw: dict[str, Any] = field(default_factory=dict)
    value_date: date | None = None


@runtime_checkable
class PaymentProvider(Protocol):
    """MTN Mobile Money, Zain Cash / M-Gurush, bank slip import (FR-FIN-03).
    Business logic never imports a vendor SDK; it talks to this."""

    name: str

    def initiate(
        self, amount: Decimal, currency: str, payer_ref: str, invoice_ref: str
    ) -> PaymentIntent: ...

    def status(self, reference: str) -> PaymentStatusResult: ...

    def verify_callback(self, request: Any) -> PaymentEvent: ...
