"""
Print the authorisation policy as a matrix.

    python manage.py permission_matrix
    python manage.py permission_matrix --check-separation

Two audiences: staff who need to see what a role can do without reading Python,
and a reviewer checking that separation of duties holds.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.roles import (
    GRADE_WRITE_PERMISSIONS,
    MONEY_WRITE_PERMISSIONS,
    ROLES,
)


class Command(BaseCommand):
    help = "Print the role × permission matrix and verify separation of duties."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--check-separation",
            action="store_true",
            help="Exit non-zero if any role holds both grade-write and money-write permissions.",
        )
        parser.add_argument(
            "--installed-only",
            action="store_true",
            help="Show only permissions whose module is installed.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        installed = {
            f"{p.content_type.app_label}.{p.codename}"
            for p in Permission.objects.select_related("content_type")
        }

        self.stdout.write(self.style.MIGRATE_HEADING("Role → permissions"))
        self.stdout.write("")

        for definition in ROLES:
            by_app: dict[str, list[str]] = defaultdict(list)
            pending = 0
            for codename in sorted(definition.permissions):
                app_label, name = codename.split(".", 1)
                is_installed = codename in installed
                if not is_installed:
                    pending += 1
                    if options["installed_only"]:
                        continue
                by_app[app_label].append(name if is_installed else f"{name} (pending)")

            self.stdout.write(self.style.HTTP_INFO(f"{definition.code} — {definition.name}"))
            if not by_app:
                self.stdout.write("    (own records only, enforced by queryset scoping)")
            for app_label, names in sorted(by_app.items()):
                self.stdout.write(f"    {app_label:<14} {', '.join(names)}")
            self.stdout.write(
                f"    → {len(definition.permissions)} declared, "
                f"{len(definition.permissions) - pending} live, {pending} pending"
            )
            self.stdout.write("")

        # ---- separation of duties ----
        self.stdout.write(self.style.MIGRATE_HEADING("Separation of duties"))
        violations: list[str] = []
        for definition in ROLES:
            held = set(definition.permissions)
            grades = held & GRADE_WRITE_PERMISSIONS
            money = held & MONEY_WRITE_PERMISSIONS
            if grades and money:
                violations.append(
                    f"{definition.code} holds both grade-write ({sorted(grades)}) "
                    f"and money-write ({sorted(money)})"
                )
            marker = "grades" if grades else ("money" if money else "neither")
            self.stdout.write(f"  {definition.code:<14} writes: {marker}")

        self.stdout.write("")
        if violations:
            message = "Separation of duties violated:\n  " + "\n  ".join(violations)
            if options["check_separation"]:
                raise CommandError(message)
            self.stdout.write(self.style.ERROR(message))
        else:
            self.stdout.write(
                self.style.SUCCESS("No role holds both grade-write and money-write permissions.")
            )
