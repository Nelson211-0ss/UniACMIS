"""
Writing audit entries, and the hash chain that makes them tamper-evident.

The chain is appended under a lock so that concurrent writers cannot interleave
and produce two rows claiming the same predecessor. On PostgreSQL that is a
transaction-scoped advisory lock, which is cheap (microseconds) and released
automatically if the process dies mid-transaction — relevant on a box that loses
power without warning.

This does serialise audited writes behind one lock. At the target of 500
concurrent users per campus each insert holds it for well under a millisecond, so
it is not the bottleneck; if Phase 7 load testing says otherwise, the escape
hatch is to shard the chain by content type and verify each chain independently.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db import connection, transaction
from django.utils import timezone

from apps.audit.models import GENESIS_HASH, AuditAction, AuditLog
from apps.core import context

logger = logging.getLogger(__name__)

# Arbitrary but fixed: the advisory-lock key for the audit chain.
_CHAIN_LOCK_KEY = 8_471_123


def _stringify(value: Any) -> str | None:
    """Render a value for storage.

    `None` is preserved as SQL NULL so that "the field was empty" stays
    distinguishable from "this row is not about a field change".
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if hasattr(value, "pk") and not isinstance(value, str | int):
        return str(value.pk)
    return str(value)


def canonical_payload(entry: AuditLog) -> str:
    """Stable serialisation of the fields the hash covers.

    Sorted keys and a fixed separator: the digest has to be reproducible years
    later by `verify_audit_chain`, so nothing about it may depend on dict order
    or formatting.
    """
    return json.dumps(
        {
            "content_type_id": entry.content_type_id,
            "object_id": entry.object_id,
            "object_repr": entry.object_repr,
            "action": entry.action,
            "field_name": entry.field_name,
            "old_value": entry.old_value,
            "new_value": entry.new_value,
            "description": entry.description,
            "reason": entry.reason,
            "actor_id": entry.actor_id,
            "actor_name": entry.actor_name,
            "actor_role": entry.actor_role,
            "ip_address": entry.ip_address,
            "request_id": entry.request_id,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def compute_row_hash(prev_hash: str, payload: str) -> str:
    return hashlib.sha256(f"{prev_hash}{payload}".encode()).hexdigest()


def _lock_chain() -> None:
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_CHAIN_LOCK_KEY])
    else:  # pragma: no cover - we deploy and test on PostgreSQL
        # Row lock on the tail as a weaker fallback.
        list(AuditLog.objects.select_for_update().order_by("-id")[:1])


def _actor_details(actor: Any | None) -> tuple[Any | None, str, str]:
    actor = actor if actor is not None else context.get_actor()
    if actor is None or not getattr(actor, "pk", None):
        return None, context.SYSTEM_ACTOR_NAME, ""

    name = ""
    for attr in ("get_full_name", "get_username"):
        getter = getattr(actor, attr, None)
        if callable(getter):
            name = str(getter() or "").strip()
            if name:
                break
    if not name:
        name = str(actor)

    role = ""
    role_getter = getattr(actor, "primary_role_code", None)
    if callable(role_getter):
        try:
            role = str(role_getter() or "")
        except Exception:  # pragma: no cover
            role = ""

    return actor, name[:150], role[:100]


def _write(
    *,
    instance: Any | None,
    action: str,
    field_name: str = "",
    old_value: Any = None,
    new_value: Any = None,
    description: str = "",
    reason: str = "",
    actor: Any | None = None,
) -> AuditLog | None:
    content_type = None
    object_id = ""
    object_repr = ""

    if instance is not None:
        try:
            content_type = ContentType.objects.get_for_model(instance)
            object_id = str(instance.pk) if getattr(instance, "pk", None) else ""
            object_repr = str(instance)[:255]
        except Exception:  # pragma: no cover
            logger.warning("Could not resolve audit target for %r", instance)

    resolved_actor, actor_name, actor_role = _actor_details(actor)

    entry = AuditLog(
        content_type=content_type,
        object_id=object_id,
        object_repr=object_repr,
        action=action,
        field_name=field_name or "",
        old_value=_stringify(old_value),
        new_value=_stringify(new_value),
        description=description[:255],
        reason=reason,
        actor=resolved_actor,
        actor_name=actor_name,
        actor_role=actor_role,
        ip_address=context.get_client_ip(),
        user_agent=context.get_user_agent(),
        request_id=context.get_request_id() or "",
    )

    with transaction.atomic():
        _lock_chain()
        prev_hash = (
            AuditLog.objects.order_by("-id").values_list("row_hash", flat=True).first()
            or GENESIS_HASH
        )
        # Set explicitly so the value hashed is exactly the value stored.
        entry.created_at = timezone.now()
        entry.prev_hash = prev_hash
        entry.row_hash = compute_row_hash(prev_hash, canonical_payload(entry))
        entry.save(force_insert=True)

    return entry


def _safe_write(sensitive: bool, **kwargs: Any) -> AuditLog | None:
    """Write an entry.

    For sensitive records (grades, money) a failure propagates, so the change it
    describes is rolled back with it. Elsewhere it is reported loudly but does not
    take the user's action down with it — a registrar should not lose a typed form
    because the audit table is full.
    """
    if sensitive:
        return _write(**kwargs)
    try:
        return _write(**kwargs)
    except Exception:
        logger.exception("Failed to write audit entry: %s", kwargs.get("action"))
        return None


# ----------------------------------------------------------------- public API


def record_change(
    *,
    instance: Any,
    field_name: str,
    old_value: Any,
    new_value: Any,
    action: str = AuditAction.UPDATE,
    reason: str = "",
    actor: Any | None = None,
) -> AuditLog | None:
    """Record one field changing value."""
    return _safe_write(
        getattr(instance, "audit_sensitive", False),
        instance=instance,
        action=action,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        actor=actor,
    )


def record_action(
    *,
    instance: Any | None,
    action: str,
    description: str = "",
    reason: str = "",
    actor: Any | None = None,
) -> AuditLog | None:
    """Record something that is not a field change: a login, an approval, an
    export, a sensitive read."""
    return _safe_write(
        getattr(instance, "audit_sensitive", False) if instance is not None else False,
        instance=instance,
        action=action,
        description=description,
        reason=reason,
        actor=actor,
    )


def record_sensitive_view(*, instance: Any, description: str = "", actor: Any | None = None):
    """NFR-SEC-03 requires logging *access to* grade and financial records, not
    only changes to them."""
    return record_action(
        instance=instance,
        action=AuditAction.VIEW_SENSITIVE,
        description=description or f"Viewed {instance._meta.verbose_name}",
        actor=actor,
    )


# ------------------------------------------------------------ chain verification


def verify_chain(start_id: int = 0, limit: int | None = None) -> dict[str, Any]:
    """Re-walk the chain and report the first break.

    Returns `{"ok", "checked", "first_broken_id", "detail"}`.
    """
    queryset = AuditLog.objects.filter(id__gt=start_id).order_by("id")
    # A sliced queryset cannot be streamed with iterator(), so bound the read
    # either by slicing or by chunking, never both.
    entries = list(queryset[:limit]) if limit else queryset.iterator(chunk_size=500)

    expected_prev = GENESIS_HASH
    if start_id:
        previous = AuditLog.objects.filter(id__lte=start_id).order_by("-id").first()
        if previous is not None:
            expected_prev = previous.row_hash

    checked = 0
    for entry in entries:
        if entry.prev_hash != expected_prev:
            return {
                "ok": False,
                "checked": checked,
                "first_broken_id": entry.id,
                "detail": (
                    f"Entry {entry.id} expects predecessor {expected_prev[:12]}… "
                    f"but records {entry.prev_hash[:12]}… — an entry was removed or altered."
                ),
            }

        recomputed = compute_row_hash(entry.prev_hash, canonical_payload(entry))
        if recomputed != entry.row_hash:
            return {
                "ok": False,
                "checked": checked,
                "first_broken_id": entry.id,
                "detail": (
                    f"Entry {entry.id} does not match its own hash — its contents were altered "
                    f"after it was written."
                ),
            }

        expected_prev = entry.row_hash
        checked += 1

    return {"ok": True, "checked": checked, "first_broken_id": None, "detail": "Chain intact."}
