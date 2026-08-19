"""
Merit list generation with quota rules (FR-ADM-06).

Pure over a list of candidates — no ORM here — so the ranking policy is
unit-testable in isolation and the ORM-facing `services.generate_merit_list` is a
thin adapter that builds `Candidate` rows and reads the result back.

Quota configuration lives on `Programme.admission_quota_rules` (JSON), e.g.:

    {
      "total_seats": 50,
      "reserved": [
        {"category": "state", "value": "warrap", "seats": 5},
        {"category": "gender", "value": "female", "seats": 10}
      ]
    }

Policy, stated once so it is not rediscovered by reading the loop:

1. Candidates rank by score, best first; a missing score ranks last, and ties
   break on application id so the result is reproducible.
2. With no `total_seats`, everyone is ranked and no one is excluded — a merit
   list without a cap is just a sorted list.
3. Reserved categories are filled first, in the order they are declared, from
   the best-ranked matching, not-yet-admitted candidates.
4. A reserved category that cannot be filled (too few matching applicants)
   returns its unused seats to the general pool rather than leaving them
   empty — the common real quota policy, and the one that avoids turning a
   quota meant to widen access into a way to shut seats entirely.
5. Remaining seats fill from the general pool in rank order.
6. `rank` reflects overall merit regardless of admission outcome — a
   candidate can rank 60th on a 50-seat programme and correctly show as not
   admitted, without their rank being renumbered around who got a seat.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class Candidate:
    application_id: int
    score: Decimal | None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MeritListEntry:
    application_id: int
    rank: int
    score: Decimal | None
    admitted: bool
    quota_category: str | None  # None means "admitted on general merit"


_UNSCORED = Decimal("-Infinity")


def _sort_key(candidate: Candidate) -> tuple[Decimal, int]:
    # Negated score for descending order; application_id ascending breaks ties
    # deterministically rather than leaning on dict/set ordering.
    score = candidate.score if candidate.score is not None else _UNSCORED
    return (-score, candidate.application_id)


def generate_merit_list(
    candidates: list[Candidate], quota_rules: dict[str, Any] | None
) -> list[MeritListEntry]:
    ranked = sorted(candidates, key=_sort_key)

    ranks: dict[int, int] = {c.application_id: i + 1 for i, c in enumerate(ranked)}
    admitted: dict[int, str | None] = {}

    total_seats = (quota_rules or {}).get("total_seats")

    if total_seats is None:
        return [
            MeritListEntry(c.application_id, ranks[c.application_id], c.score, True, None)
            for c in ranked
        ]

    reserved = (quota_rules or {}).get("reserved") or []
    for bucket in reserved:
        category, value, seats = bucket["category"], bucket["value"], int(bucket["seats"])
        filled = 0
        for candidate in ranked:
            if filled >= seats:
                break
            if candidate.application_id in admitted:
                continue
            if candidate.attributes.get(category) != value:
                continue
            admitted[candidate.application_id] = f"{category}:{value}"
            filled += 1
        # Seats this bucket could not fill are simply never consumed — they
        # fall through to the general pool below (policy #4 above).

    remaining_seats = max(0, total_seats - len(admitted))
    for candidate in ranked:
        if remaining_seats <= 0:
            break
        if candidate.application_id in admitted:
            continue
        admitted[candidate.application_id] = None
        remaining_seats -= 1

    return [
        MeritListEntry(
            application_id=c.application_id,
            rank=ranks[c.application_id],
            score=c.score,
            admitted=c.application_id in admitted,
            quota_category=admitted.get(c.application_id),
        )
        for c in ranked
    ]
