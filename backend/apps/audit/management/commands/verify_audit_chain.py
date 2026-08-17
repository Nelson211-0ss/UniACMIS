"""
Verify the audit log's hash chain.

    python manage.py verify_audit_chain

Exits non-zero on a break, so it can run from cron and raise an alarm. This is
the check that turns the audit log from something that *records* changes into
something that can *prove* it was not edited afterwards (FR-RPT-04).
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.audit.models import AuditLog
from apps.audit.services import verify_chain


class Command(BaseCommand):
    help = "Verify the integrity of the audit log hash chain."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--start-id",
            type=int,
            default=0,
            help="Verify from this entry id onward (default: the whole chain).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Stop after this many entries.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        total = AuditLog.objects.count()
        if total == 0:
            self.stdout.write(self.style.WARNING("Audit log is empty — nothing to verify."))
            return

        self.stdout.write(f"Verifying audit chain ({total} entries)…")
        result = verify_chain(start_id=options["start_id"], limit=options["limit"])

        if result["ok"]:
            self.stdout.write(
                self.style.SUCCESS(f"Chain intact: {result['checked']} entries verified.")
            )
            return

        # CommandError exits non-zero, which is what a cron alert hooks onto.
        raise CommandError(
            f"AUDIT CHAIN BROKEN at entry {result['first_broken_id']} "
            f"after {result['checked']} valid entries.\n{result['detail']}\n"
            "Treat this as a potential tampering incident: preserve a database "
            "snapshot before making any further changes."
        )
