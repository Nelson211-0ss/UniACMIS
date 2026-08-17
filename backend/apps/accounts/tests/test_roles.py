"""
Role grants, revocations and `seed_roles` (NFR-SEC-01, NFR-MAINT-03).
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import IntegrityError, transaction

from apps.accounts.models import Role, UserRole
from apps.accounts.roles import ROLE_CODES, ROLES
from apps.accounts.services import (
    UnknownRole,
    effective_permissions,
    grant_role,
    resync_groups,
    revoke_role,
)
from apps.audit.models import AuditAction, AuditLog

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------ seed_roles


def test_seed_roles_creates_every_declared_role(roles):
    assert Role.objects.count() == len(ROLES)
    assert set(Role.objects.values_list("code", flat=True)) == set(ROLE_CODES)


def test_every_role_gets_a_group(roles):
    for role in Role.objects.all():
        assert role.group_id is not None


def test_seed_roles_is_idempotent(roles):
    before_roles = Role.objects.count()
    before_groups = Group.objects.count()
    before_perms = {
        role.code: role.group.permissions.count() for role in Role.objects.select_related("group")
    }

    call_command("seed_roles", verbosity=0)

    assert Role.objects.count() == before_roles
    assert Group.objects.count() == before_groups
    assert {
        role.code: role.group.permissions.count() for role in Role.objects.select_related("group")
    } == before_perms


def test_seed_roles_grants_real_permissions(roles):
    registrar = Role.objects.get(code="registrar")
    codenames = set(registrar.group.permissions.values_list("codename", flat=True))
    assert "add_student" in codenames
    assert "view_student" in codenames


def test_permissions_for_uninstalled_modules_are_skipped_not_fatal(roles):
    """The policy declares finance and examinations permissions before those
    modules exist. Seeding must succeed and simply leave them pending."""
    finance = Role.objects.get(code="finance")
    codenames = {
        f"{p.content_type.app_label}.{p.codename}"
        for p in finance.group.permissions.select_related("content_type")
    }
    assert "registry.view_student" in codenames  # exists today
    assert not any(c.startswith("finance.") for c in codenames)  # pending


def test_seed_roles_applies_newly_available_permissions_on_a_later_run(roles):
    """Simulates a module landing: remove a permission from the group, re-run, and
    it comes back — which is what makes the command safe to run on every deploy.
    """
    registrar = Role.objects.get(code="registrar")
    permission = registrar.group.permissions.get(codename="add_student")
    registrar.group.permissions.remove(permission)
    assert not registrar.group.permissions.filter(codename="add_student").exists()

    call_command("seed_roles", verbosity=0)

    assert registrar.group.permissions.filter(codename="add_student").exists()


def test_prune_removes_permissions_the_policy_no_longer_lists(roles):
    """`--prune` is the corrective run: it makes the database match roles.py
    exactly, including taking away a permission granted by hand."""
    from django.contrib.auth.models import Permission

    from apps.accounts.roles import permissions_for

    registrar = Role.objects.get(code="registrar")
    # A permission the registrar policy genuinely does not list (ICT holds it).
    stray = Permission.objects.get(codename="add_user", content_type__app_label="accounts")
    assert "accounts.add_user" not in permissions_for("registrar")

    registrar.group.permissions.add(stray)
    assert registrar.group.permissions.filter(pk=stray.pk).exists()

    call_command("seed_roles", "--prune", verbosity=0)

    assert not registrar.group.permissions.filter(pk=stray.pk).exists()
    # Pruning must not strip what the policy does list.
    assert registrar.group.permissions.filter(codename="add_student").exists()


def test_the_default_run_is_additive(roles):
    """Without `--prune` a deliberate local exception granted in the admin
    survives a deploy, rather than being silently revoked."""
    from django.contrib.auth.models import Permission

    registrar = Role.objects.get(code="registrar")
    stray = Permission.objects.get(codename="add_user", content_type__app_label="accounts")
    registrar.group.permissions.add(stray)

    call_command("seed_roles", verbosity=0)

    assert registrar.group.permissions.filter(pk=stray.pk).exists()


# ---------------------------------------------------------------- granting


def test_granting_a_role_adds_the_group(roles, user_factory):
    user = user_factory()
    grant_role(user, "registrar")

    assert user.role_codes() == ["registrar"]
    assert user.groups.filter(name="registrar").exists()
    assert user.has_perm("registry.add_student")


def test_granting_is_idempotent(roles, user_factory):
    user = user_factory()
    first = grant_role(user, "lecturer")
    second = grant_role(user, "lecturer")

    assert first.pk == second.pk
    assert UserRole.objects.filter(user=user, revoked_at__isnull=True).count() == 1


def test_an_unknown_role_is_refused(roles, user_factory):
    with pytest.raises(UnknownRole, match="No role with code"):
        grant_role(user_factory(), "vice_chancellor")


def test_a_grant_records_who_did_it(roles, user_factory):
    granter = user_factory(role="ict_admin")
    target = user_factory()

    assignment = grant_role(target, "finance", granted_by=granter, reason="Joined the bursary")

    assert assignment.granted_by == granter
    assert assignment.reason == "Joined the bursary"


def test_a_grant_is_audited(roles, user_factory):
    granter = user_factory(role="ict_admin")
    target = user_factory()

    grant_role(target, "finance", granted_by=granter, reason="Joined the bursary")

    entry = AuditLog.objects.filter(action=AuditAction.ROLE_GRANT).first()
    assert entry is not None
    assert "finance" in entry.description
    assert entry.actor_id == granter.pk


def test_two_active_grants_of_the_same_role_are_impossible(roles, user_factory):
    user = user_factory()
    role = Role.objects.get(code="lecturer")
    UserRole.objects.create(user=user, role=role)

    with pytest.raises(IntegrityError), transaction.atomic():
        UserRole.objects.create(user=user, role=role)


def test_a_user_may_hold_several_roles(roles, user_factory):
    user = user_factory()
    grant_role(user, "lecturer")
    grant_role(user, "hod")
    assert set(user.role_codes()) == {"hod", "lecturer"}


# --------------------------------------------------------------- revoking


def test_revoking_removes_the_group_but_keeps_the_record(roles, user_factory):
    user = user_factory(role="finance")
    revoke_role(user, "finance", reason="Moved department")

    assert user.role_codes() == []
    assert not user.groups.filter(name="finance").exists()
    # The evidence that the role was once held survives.
    assert UserRole.objects.filter(user=user, role__code="finance").exists()
    assert UserRole.objects.get(user=user, role__code="finance").revoked_at is not None


def test_revoking_is_audited(roles, user_factory):
    admin = user_factory(role="ict_admin")
    user = user_factory(role="finance")

    revoke_role(user, "finance", revoked_by=admin, reason="Left the university")

    entry = AuditLog.objects.filter(action=AuditAction.ROLE_REVOKE).first()
    assert entry is not None
    assert entry.reason == "Left the university"


def test_revoking_a_role_not_held_is_a_no_op(roles, user_factory):
    user = user_factory()
    revoke_role(user, "finance")  # must not raise
    assert user.role_codes() == []


def test_a_role_can_be_granted_again_after_revocation(roles, user_factory):
    user = user_factory()
    grant_role(user, "library")
    revoke_role(user, "library", reason="Transferred out")
    grant_role(user, "library", reason="Transferred back")

    assert user.role_codes() == ["library"]
    # Two rows: the history is preserved rather than overwritten.
    assert UserRole.objects.filter(user=user, role__code="library").count() == 2


def test_resync_rebuilds_group_membership_from_assignments(roles, user_factory):
    """Repair path: if groups and assignments ever disagree, the assignments win."""
    user = user_factory(role="registrar")
    user.groups.clear()
    assert not user.has_perm("registry.add_student")

    resync_groups(user)
    user = type(user).objects.get(pk=user.pk)  # drop the permission cache
    assert user.has_perm("registry.add_student")


# ----------------------------------------------------------- effective perms


def test_effective_permissions_lists_the_role_permissions(roles, user_factory):
    user = user_factory(role="registrar")
    permissions = effective_permissions(user)
    assert "registry.add_student" in permissions
    assert "finance.add_payment" not in permissions


def test_a_superuser_gets_everything(roles, user_factory):
    user = user_factory(email="super@test.ss", is_superuser=True, is_staff=True)
    assert "registry.add_student" in effective_permissions(user)


def test_primary_role_is_stable_for_the_audit_trail(roles, user_factory):
    user = user_factory()
    grant_role(user, "lecturer")
    grant_role(user, "hod")
    # Deterministic, so the trail reads consistently for a multi-role user.
    assert user.primary_role_code() == "hod"
    assert user.primary_role_code() == "hod"


def test_a_superuser_is_labelled_as_such_in_the_trail(roles, user_factory):
    user = user_factory(email="root@test.ss", is_superuser=True)
    assert user.primary_role_code() == "superuser"
