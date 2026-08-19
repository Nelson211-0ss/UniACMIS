"""
Invoice and receipt numbers.

A separate, simpler scheme from the student-ID template, the same way
`admissions.id_generation` keeps its application reference apart from it: an
invoice number just needs to be unique and traceable for one academic year,
not a lifelong identifier printed on a certificate — made configurable the
same way if that turns out to matter in practice.
"""

from __future__ import annotations

from apps.core.models import IdSequence


def generate_invoice_number(academic_year_name: str) -> str:
    year = str(academic_year_name).split("/")[0].strip()
    sequence = IdSequence.allocate(f"invoice_no:{year}")
    return f"INV/{year}/{sequence:05d}"


def generate_receipt_number(academic_year_name: str) -> str:
    year = str(academic_year_name).split("/")[0].strip()
    sequence = IdSequence.allocate(f"receipt_no:{year}")
    return f"RCT/{year}/{sequence:05d}"
