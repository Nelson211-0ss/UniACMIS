"""Adapter that satisfies `apps.core.ports.AuditPort`."""

from __future__ import annotations

from typing import Any

from apps.audit import services


class DjangoAuditPort:
    """Registered into the core registry at app-ready, so `core` can write audit
    entries without importing this app."""

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
    ) -> None:
        services.record_change(
            instance=instance,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            action=action,
            reason=reason,
            actor=actor,
        )

    def record_action(
        self,
        *,
        instance: Any | None,
        action: str,
        description: str = "",
        reason: str = "",
        actor: Any | None = None,
    ) -> None:
        services.record_action(
            instance=instance,
            action=action,
            description=description,
            reason=reason,
            actor=actor,
        )
