"""
Hold aggregation.

One question — "may this student proceed?" — asked by registration (FR-ENR-03),
result publication (FR-EXM-06) and graduation clearance (FR-DOC-04). Each
module that can say no registers a `HoldProvider`; this collects the answers.

A provider that raises is treated as a **blocking** hold rather than silently
ignored: if the finance module is unreachable we do not know that fees are paid,
and letting an unpaid student register is the more expensive mistake.
"""

from __future__ import annotations

import logging

from apps.core.ports import Hold, HoldProvider
from apps.core.services.registry import registry

logger = logging.getLogger(__name__)


def collect_holds(student_id: int) -> list[Hold]:
    holds: list[Hold] = []
    for provider in registry.get_all(HoldProvider):
        source = getattr(provider, "source", type(provider).__name__)
        try:
            holds.extend(provider.holds_for(student_id))
        except Exception:
            logger.exception("Hold provider %s failed for student %s", source, student_id)
            holds.append(
                Hold(
                    code="hold_check_failed",
                    message=(
                        f"Could not confirm clearance from {source}. "
                        "Resolve this before proceeding."
                    ),
                    source=source,
                    blocking=True,
                )
            )
    return holds


def blocking_holds(student_id: int) -> list[Hold]:
    return [h for h in collect_holds(student_id) if h.blocking]


def is_clear(student_id: int) -> bool:
    return not blocking_holds(student_id)
