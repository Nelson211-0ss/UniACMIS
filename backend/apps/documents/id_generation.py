"""Document serial numbers — the identifier printed on the physical
document and encoded into its verification QR code, so it has to be unique
and never reused, unlike an invoice number (see `apps.finance.id_generation`)."""

from __future__ import annotations

from apps.core.models import IdSequence
from apps.documents.models import DocumentType

_PREFIX = {
    DocumentType.TRANSCRIPT: "TRX",
    DocumentType.CERTIFICATE: "CERT",
}


def generate_serial_number(document_type: str, year: str) -> str:
    prefix = _PREFIX[document_type]
    sequence = IdSequence.allocate(f"document_serial:{document_type}:{year}")
    return f"{prefix}/{year}/{sequence:05d}"
