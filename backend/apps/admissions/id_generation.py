"""Application reference numbers.

A separate, simpler scheme from the student-ID template (FR-REG-01's format is
about faculty/programme/year and is printed on certificates for decades; an
application reference just needs to be unique and traceable for one intake
cycle) — kept as its own function so the two can evolve independently, and
made configurable the same way if that turns out to matter in practice.
"""

from __future__ import annotations

from apps.core.models import IdSequence


def generate_reference_number(academic_year_name: str) -> str:
    year = str(academic_year_name).split("/")[0].strip()
    sequence = IdSequence.allocate(f"application_ref:{year}")
    return f"APP/{year}/{sequence:05d}"
