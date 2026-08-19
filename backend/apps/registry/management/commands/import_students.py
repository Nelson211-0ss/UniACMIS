"""
Bulk-import legacy student records from a CSV file (NFR-DATA-03).

    python manage.py import_students students.csv              # dry run — validates only
    python manage.py import_students students.csv --commit      # writes, only if every row is valid

Required columns: first_name, last_name, gender, programme_code, entry_academic_year.
Optional: student_id, middle_name, date_of_birth (YYYY-MM-DD), national_id_number,
state_of_origin, has_disability, disability_details, nationality, phone, email,
curriculum_version.

`programme_code` and `entry_academic_year` are natural keys (a programme's `code`,
an academic year's `name` such as "2026/2027") — the spreadsheet a registrar
already has, not internal database ids.
"""

from __future__ import annotations

import csv
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.registry.services import import_students


class Command(BaseCommand):
    help = "Bulk-import legacy student records from a CSV file, with validation and rollback."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("csv_path")
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Write the records. Without this flag, only validates and reports.",
        )
        parser.add_argument("--reason", default="Bulk legacy import")

    def handle(self, *args: Any, **options: Any) -> None:
        csv_path = options["csv_path"]
        try:
            with open(csv_path, newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh))
        except OSError as exc:
            raise CommandError(f"Could not read '{csv_path}': {exc}") from exc

        if not rows:
            raise CommandError("The file has no data rows.")

        result = import_students(rows, commit=options["commit"], reason=options["reason"])

        self.stdout.write(f"Rows read:     {result['total']}")
        self.stdout.write(f"Rows valid:    {result['valid']}")
        self.stdout.write(f"Rows created:  {result['created']}")

        if result["errors"]:
            self.stdout.write(self.style.ERROR(f"Rows rejected: {len(result['errors'])}"))
            for entry in result["errors"]:
                for field, message in entry["errors"].items():
                    self.stdout.write(f"  row {entry['row']}: {field}: {message}")
            if options["commit"]:
                self.stdout.write(
                    self.style.ERROR("Nothing was written — fix the rows above and re-run.")
                )
            raise CommandError(f"{len(result['errors'])} row(s) failed validation.")

        if options["commit"]:
            self.stdout.write(self.style.SUCCESS(f"Created {result['created']} student(s)."))
        else:
            self.stdout.write(
                self.style.SUCCESS("Dry run — every row is valid. Re-run with --commit to write.")
            )
