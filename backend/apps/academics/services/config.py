"""
Institutional configuration, exposed as functions.

Other modules read configuration through here rather than importing
`academics.models.Institution`, which keeps the module boundary intact and gives
every caller the same fallback behaviour when setup has not run yet.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings

from apps.academics.models import Institution

DEFAULT_STUDENT_ID_TEMPLATE = "{faculty}/{programme}/{year}/{seq:04d}"
DEFAULT_STAFF_ID_TEMPLATE = "STF/{year}/{seq:04d}"
DEFAULT_ATTENDANCE_THRESHOLD = Decimal("75.00")


def institution() -> Institution | None:
    return Institution.get()


def student_id_template() -> str:
    inst = Institution.get()
    return (inst.student_id_template if inst else None) or DEFAULT_STUDENT_ID_TEMPLATE


def staff_id_template() -> str:
    inst = Institution.get()
    return (inst.staff_id_template if inst else None) or DEFAULT_STAFF_ID_TEMPLATE


def attendance_threshold() -> Decimal:
    """Minimum attendance % before a student may be barred from exams (FR-ATT-02)."""
    inst = Institution.get()
    return inst.attendance_threshold_percent if inst else DEFAULT_ATTENDANCE_THRESHOLD


def base_currency() -> str:
    inst = Institution.get()
    return inst.default_currency if inst else settings.DEFAULT_CURRENCY


def secondary_currency() -> str:
    inst = Institution.get()
    return (inst.secondary_currency if inst else None) or settings.SECONDARY_CURRENCY


def institution_name() -> str:
    inst = Institution.get()
    return inst.name if inst else "UniACMIS"
