"""
Account and role operations.

Role grants go through here rather than through the ORM directly, because three
things must happen together: the assignment row, the Django group membership that
actually carries the permissions, and the audit entry. Doing two of the three is
a silent authorisation bug.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User, UserRole
from apps.audit.models import AuditAction
from apps.audit.services import record_action
from apps.core.exceptions import DomainError

logger = logging.getLogger(__name__)


class UnknownRole(DomainError):
    code = "unknown_role"
    message = "That role does not exist."


@transaction.atomic
def grant_role(
    user: User,
    role_code: str,
    *,
    granted_by: User | None = None,
    reason: str = "",
) -> UserRole:
    """Give `user` a role. Idempotent — re-granting an active role is a no-op."""
    try:
        role = Role.objects.get(code=role_code)
    except Role.DoesNotExist as exc:
        raise UnknownRole(f"No role with code '{role_code}'. Run `seed_roles`.") from exc

    existing = UserRole.objects.filter(user=user, role=role, revoked_at__isnull=True).first()
    if existing is not None:
        return existing

    assignment = UserRole.objects.create(
        user=user,
        role=role,
        granted_by=granted_by,
        reason=reason,
    )

    if role.group_id:
        user.groups.add(role.group)

    record_action(
        instance=user,
        action=AuditAction.ROLE_GRANT,
        description=f"Granted role '{role.code}'",
        reason=reason,
        actor=granted_by,
    )
    return assignment


@transaction.atomic
def revoke_role(
    user: User,
    role_code: str,
    *,
    revoked_by: User | None = None,
    reason: str = "",
) -> None:
    """Revoke a role. The assignment row is marked revoked, never deleted."""
    try:
        role = Role.objects.get(code=role_code)
    except Role.DoesNotExist as exc:
        raise UnknownRole(f"No role with code '{role_code}'.") from exc

    assignments = UserRole.objects.filter(user=user, role=role, revoked_at__isnull=True)
    if not assignments.exists():
        return

    assignments.update(revoked_at=timezone.now(), revoked_by=revoked_by, reason=reason)

    if role.group_id:
        user.groups.remove(role.group)

    record_action(
        instance=user,
        action=AuditAction.ROLE_REVOKE,
        description=f"Revoked role '{role.code}'",
        reason=reason,
        actor=revoked_by,
    )


def resync_groups(user: User) -> None:
    """Rebuild group membership from the active role assignments.

    Repair tool: if group membership and role assignments ever disagree, the
    assignments are the source of truth.
    """
    groups = [
        role.group
        for role in user.active_roles().select_related("group")
        if role.group_id is not None
    ]
    user.groups.set(groups)


# --------------------------------------------------------------- sign-in state


def record_successful_login(user: User, ip: str | None = None) -> None:
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_ip = ip
    user.last_login = timezone.now()
    user.save(
        update_fields=["failed_login_attempts", "locked_until", "last_login_ip", "last_login"]
    )
    record_action(
        instance=user,
        action=AuditAction.LOGIN,
        description=f"Signed in ({user.primary_role_code() or 'no role'})",
        actor=user,
    )


def record_failed_login(email: str, *, max_attempts: int, lockout_minutes: int) -> None:
    """Count a failed attempt and lock the account once the threshold is hit.

    Failures are audited even when the address matches no account: a run of
    attempts against unknown addresses is itself the signal worth keeping.
    """
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        record_action(
            instance=None,
            action=AuditAction.LOGIN_FAILED,
            description=f"Failed sign-in for unknown address '{email[:120]}'",
        )
        return

    user.failed_login_attempts += 1
    fields = ["failed_login_attempts"]

    if user.failed_login_attempts >= max_attempts:
        user.locked_until = timezone.now() + timedelta(minutes=lockout_minutes)
        fields.append("locked_until")

    user.save(update_fields=fields)

    record_action(
        instance=user,
        action=AuditAction.LOGIN_FAILED,
        description=(
            f"Failed sign-in ({user.failed_login_attempts}/{max_attempts})"
            + (" — account locked" if user.locked_until else "")
        ),
        actor=user,
    )


def record_logout(user: User) -> None:
    record_action(
        instance=user,
        action=AuditAction.LOGOUT,
        description="Signed out",
        actor=user,
    )


def effective_permissions(user: User) -> list[str]:
    """All permission codenames the user holds, for the /me payload.

    The frontend uses this to hide what it should not offer. It is a usability
    measure only — the API is the actual boundary.
    """
    if user.is_superuser:
        from django.contrib.auth.models import Permission

        return sorted(
            f"{app_label}.{codename}"
            for app_label, codename in Permission.objects.values_list(
                "content_type__app_label", "codename"
            )
        )
    return sorted(user.get_all_permissions())
