"""
The sync engine (NFR-AVAIL-01).

Guarantees, in the order they matter for a campus with unreliable power and
network:

1. **Replay is safe.** `client_op_id` is unique. A retried operation returns the
   result of the first application and changes nothing. Clients retry whole
   batches after a dropped connection, so this is the normal path.
2. **One bad operation does not sink the batch.** Each operation runs in its own
   savepoint and reports its own status; ninety good rows still land.
3. **Nothing is silently overwritten.** `LAST_WRITE_WINS` records the value it
   replaced in the audit trail, so a lost update is reconstructable.
   `FLAG_FOR_REVIEW` refuses to apply and files a conflict for a human.
4. **Server time is authoritative.** Client timestamps are stored, and used only
   to order one device's own stream. Devices' clocks are often wrong, and a fast
   clock must not be able to win an argument about a grade.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction

from apps.core import ports
from apps.core.exceptions import DomainError, SyncConflictDetected
from apps.core.models import (
    ConflictPolicy,
    SyncConflict,
    SyncOperation,
    SyncStatus,
)
from apps.core.sync.handlers import SyncOperationInput, get_handler

logger = logging.getLogger(__name__)


@dataclass
class OperationOutcome:
    client_op_id: str
    entity: str
    status: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    conflict_id: int | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "client_op_id": self.client_op_id,
            "entity": self.entity,
            "status": self.status,
        }
        if self.result is not None:
            payload["result"] = self.result
        if self.error is not None:
            payload["error"] = self.error
        if self.conflict_id is not None:
            payload["conflict_id"] = self.conflict_id
        return payload


def _rejected(op: SyncOperationInput, code: str, message: str) -> OperationOutcome:
    return OperationOutcome(
        client_op_id=str(op.client_op_id),
        entity=op.entity,
        status=SyncStatus.REJECTED,
        error={"code": code, "message": message},
    )


def apply_operation(op: SyncOperationInput, actor: Any) -> OperationOutcome:
    """Apply a single operation. Never raises for expected failures."""

    handler = get_handler(op.entity)
    if handler is None:
        return _rejected(
            op,
            "unknown_entity",
            f"No sync handler is registered for '{op.entity}'.",
        )

    if op.action not in handler.actions:
        return _rejected(
            op,
            "unsupported_action",
            f"'{op.entity}' does not support the '{op.action}' action.",
        )

    if not (actor and actor.has_perm(handler.required_permission)):
        return _rejected(
            op,
            "permission_denied",
            f"You do not have permission to sync '{op.entity}'.",
        )

    # ---- idempotency: claim the operation id, or recognise a replay ----
    try:
        with transaction.atomic():
            record = SyncOperation.objects.create(
                client_op_id=op.client_op_id,
                entity=op.entity,
                action=op.action,
                payload=op.payload,
                client_timestamp=op.client_timestamp,
                device_id=op.device_id or "",
                submitted_by=actor if getattr(actor, "pk", None) else None,
                status=SyncStatus.PENDING,
            )
    except IntegrityError:
        existing = SyncOperation.objects.filter(client_op_id=op.client_op_id).first()
        if existing is None:  # pragma: no cover - only on a non-unique failure
            return _rejected(op, "sync_error", "Could not record the operation.")
        return OperationOutcome(
            client_op_id=str(op.client_op_id),
            entity=existing.entity,
            status=SyncStatus.DUPLICATE,
            result=existing.result,
        )

    # ---- apply ----
    try:
        with transaction.atomic():
            result = handler.apply(op, actor)

            target = result.pop("_target", None) if isinstance(result, dict) else None
            record.status = SyncStatus.APPLIED
            record.result = result
            if target is not None and getattr(target, "pk", None):
                record.target_content_type = ContentType.objects.get_for_model(target)
                record.target_object_id = str(target.pk)
            record.save(
                update_fields=[
                    "status",
                    "result",
                    "target_content_type",
                    "target_object_id",
                ]
            )

        if handler.conflict_policy == ConflictPolicy.LAST_WRITE_WINS:
            _audit_overwrites(record, result)

        return OperationOutcome(
            client_op_id=str(op.client_op_id),
            entity=op.entity,
            status=SyncStatus.APPLIED,
            result=result,
        )

    except SyncConflictDetected as exc:
        conflict = _record_conflict(record, exc)
        return OperationOutcome(
            client_op_id=str(op.client_op_id),
            entity=op.entity,
            status=SyncStatus.CONFLICT,
            error={"code": "sync_conflict", "message": exc.message},
            conflict_id=conflict.pk,
        )

    except DjangoValidationError as exc:
        details = (
            exc.message_dict if hasattr(exc, "message_dict") else {"errors": list(exc.messages)}
        )
        _mark_rejected(record, str(details))
        return OperationOutcome(
            client_op_id=str(op.client_op_id),
            entity=op.entity,
            status=SyncStatus.REJECTED,
            error={
                "code": "validation_error",
                "message": "The queued data is not valid.",
                "details": details,
            },
        )

    except DomainError as exc:
        _mark_rejected(record, exc.message)
        return OperationOutcome(
            client_op_id=str(op.client_op_id),
            entity=op.entity,
            status=SyncStatus.REJECTED,
            error={"code": exc.code, "message": exc.message, "details": exc.details},
        )

    except Exception as exc:  # unexpected: keep the batch alive, keep the evidence
        logger.exception("Sync handler %s failed", op.entity)
        _mark_rejected(record, f"{exc.__class__.__name__}: {exc}")
        return OperationOutcome(
            client_op_id=str(op.client_op_id),
            entity=op.entity,
            status=SyncStatus.REJECTED,
            error={"code": "sync_error", "message": "The operation could not be applied."},
        )


def _mark_rejected(record: SyncOperation, detail: str) -> None:
    # Written outside the rolled-back transaction so the evidence survives.
    SyncOperation.objects.filter(pk=record.pk).update(
        status=SyncStatus.REJECTED, error_detail=detail[:2000]
    )


def _record_conflict(record: SyncOperation, exc: SyncConflictDetected) -> SyncConflict:
    SyncOperation.objects.filter(pk=record.pk).update(
        status=SyncStatus.CONFLICT, error_detail=exc.message[:2000]
    )

    content_type = None
    object_id = ""
    if exc.target is not None and getattr(exc.target, "pk", None):
        content_type = ContentType.objects.get_for_model(exc.target)
        object_id = str(exc.target.pk)

    return SyncConflict.objects.create(
        sync_operation=record,
        entity=record.entity,
        target_content_type=content_type,
        target_object_id=object_id,
        field_name=exc.field_name,
        server_value="" if exc.server_value is None else str(exc.server_value),
        client_value="" if exc.client_value is None else str(exc.client_value),
        server_updated_at=exc.server_updated_at,
        client_timestamp=record.client_timestamp,
    )


def _audit_overwrites(record: SyncOperation, result: Any) -> None:
    """Record values a last-write-wins sync replaced.

    A handler reports what it overwrote via `overwrote`:
        {"overwrote": [{"field": "status", "old": "present", "new": "absent"}]}
    Without this an offline sync could quietly discard an earlier value with no
    trace, which is exactly what the audit requirement exists to prevent.
    """
    if not isinstance(result, dict):
        return
    overwrites = result.get("overwrote") or []
    if not overwrites:
        return

    target = record.target
    for change in overwrites:
        ports.audit().record_change(
            instance=target if target is not None else record,
            field_name=str(change.get("field", "")),
            old_value=change.get("old"),
            new_value=change.get("new"),
            action="sync_overwrite",
            reason=(
                f"Offline sync (device={record.device_id or 'unknown'}, "
                f"op={record.client_op_id}) replaced an earlier value."
            ),
        )


def apply_batch(operations: list[SyncOperationInput], actor: Any) -> list[dict[str, Any]]:
    """Apply operations in submission order, independently of one another."""
    return [apply_operation(op, actor).as_dict() for op in operations]
