"""
Apply the RBAC policy in `apps/accounts/roles.py` to the database.

    python manage.py seed_roles

Idempotent and production-safe — intended to run on every deploy. Adding a
permission to a role therefore means editing one file and redeploying, with no
migration and no manual clicking in the admin.

Permissions belonging to modules that are not installed yet are reported as
pending rather than treated as errors: the policy is written ahead of the phases
that implement it.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Role
from apps.accounts.roles import ROLES


class Command(BaseCommand):
    help = "Create or update roles, groups and their permissions from roles.py."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--prune",
            action="store_true",
            help="Remove permissions from a role's group that the policy no longer lists.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        prune = options["prune"]

        # One query instead of one per permission: this runs on every deploy.
        available: dict[str, Permission] = {
            f"{p.content_type.app_label}.{p.codename}": p
            for p in Permission.objects.select_related("content_type")
        }

        total_pending: dict[str, list[str]] = {}

        for definition in ROLES:
            group, _ = Group.objects.get_or_create(name=definition.code)
            role, created = Role.objects.update_or_create(
                code=definition.code,
                defaults={
                    "name": definition.name,
                    "description": definition.description,
                    "group": group,
                    "is_system": True,
                },
            )

            resolved: list[Permission] = []
            pending: list[str] = []
            for codename in definition.permissions:
                permission = available.get(codename)
                if permission is None:
                    pending.append(codename)
                else:
                    resolved.append(permission)

            before_ids = set(group.permissions.values_list("pk", flat=True))
            resolved_ids = {p.pk for p in resolved}

            if prune:
                group.permissions.set(resolved)
                changed = before_ids != resolved_ids
            else:
                # Additive by default, so a permission granted deliberately in the
                # admin for a local exception is not silently taken away by a deploy.
                group.permissions.add(*resolved)
                changed = not resolved_ids.issubset(before_ids)

            if pending:
                total_pending[definition.code] = pending

            # Distinct from `created`: a role seeded before still reports
            # "unchanged" here on every ordinary redeploy, and only "updated"
            # the one time the policy in roles.py actually adds something —
            # which is what makes a stretch of identical "updated N" lines on
            # every deploy worth noticing as a bug rather than routine noise.
            verb = "created" if created else ("updated" if changed else "unchanged")
            self.stdout.write(
                f"  {role.code:<14} {verb:<8} "
                f"{len(resolved):>3} permission(s)"
                + (f", {len(pending)} pending" if pending else "")
            )

        self.stdout.write(self.style.SUCCESS(f"Applied {len(ROLES)} role(s)."))

        if total_pending:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "Pending permissions — their modules are not installed yet. "
                    "They are applied automatically once the module lands:"
                )
            )
            for code, codenames in total_pending.items():
                modules = sorted({c.split(".")[0] for c in codenames})
                self.stdout.write(f"  {code:<14} {len(codenames):>3} from {', '.join(modules)}")
