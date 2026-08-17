"""
Sync handler contract and registry.

A module makes one of its writes offline-capable by registering a handler. The
engine owns idempotency, permissions, transactions and conflict bookkeeping; the
handler owns only "apply this payload".

    @register_handler
    class AttendanceRecordHandler:
        entity = "attendance.session_record"
        actions = ("create", "update")
        conflict_policy = ConflictPolicy.LAST_WRITE_WINS
        required_permission = "attendance.add_sessionrecord"

        def apply(self, op, actor):
            ...
            return {"id": record.pk}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from apps.core.models import ConflictPolicy


@dataclass(frozen=True)
class SyncOperationInput:
    """One queued client operation."""

    client_op_id: str
    entity: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    client_timestamp: datetime | None = None
    device_id: str = ""


@runtime_checkable
class SyncHandler(Protocol):
    entity: str
    actions: tuple[str, ...]
    conflict_policy: str
    required_permission: str

    def apply(self, op: SyncOperationInput, actor: Any) -> dict[str, Any]:
        """Apply the operation and return a JSON-serialisable result.

        Raise `SyncConflictDetected` for a divergent concurrent write, or
        `django.core.exceptions.ValidationError` / `DomainError` for bad data.
        Runs inside a transaction the engine controls.
        """
        ...


_handlers: dict[str, SyncHandler] = {}


def register_handler(handler: Any) -> Any:
    """Register a handler class (instantiated) or an instance.

    Idempotent: re-registration replaces, because AppConfig.ready() can run more
    than once under the test runner.
    """
    instance = handler() if isinstance(handler, type) else handler

    for attr in ("entity", "actions", "conflict_policy", "required_permission"):
        if not hasattr(instance, attr):
            raise TypeError(f"Sync handler {instance!r} is missing `{attr}`.")

    if instance.conflict_policy not in ConflictPolicy.values:
        raise TypeError(
            f"Sync handler {instance.entity} declares unknown conflict policy "
            f"{instance.conflict_policy!r}."
        )

    _handlers[instance.entity] = instance
    return handler


def get_handler(entity: str) -> SyncHandler | None:
    return _handlers.get(entity)


def registered_entities() -> dict[str, str]:
    """entity → conflict policy, for the discovery endpoint and the admin."""
    return {entity: h.conflict_policy for entity, h in sorted(_handlers.items())}


def clear_handlers() -> None:
    """Test seam."""
    _handlers.clear()
