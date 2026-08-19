"""
Entry-requirement screening (FR-ADM-03).

Pure functions over primitives, in the same spirit as `academics.services.grading`
— testable without touching the database, and reusable from the admin, the API,
and the merit-list ranking.

Phase 2 screens the one thing consistently available at application time: the
previous certificate's overall grade against `Programme.entry_requirements`.
Subject-level requirements are surfaced as a manual-verification note rather than
silently dropped — there is no transcript model yet to check them against, and
pretending otherwise would be worse than saying so.
"""

from __future__ import annotations

from typing import Any

# South Sudan Certificate / WASSCE-style ordinal, best first. A previous_grade
# outside this list (a foreign qualification, an unrecognised scale) is treated
# as unverifiable rather than as a failure — that determination needs a human.
GRADE_ORDER = ["A", "B", "C", "D", "E", "F"]


def _rank(grade: str) -> int | None:
    grade = grade.strip().upper()
    return GRADE_ORDER.index(grade) if grade in GRADE_ORDER else None


def evaluate_entry_requirements(
    entry_requirements: dict[str, Any], previous_grade: str
) -> list[str]:
    """Warnings for a reviewer, not a hard gate — an eligibility pre-screen
    informs the committee's decision (FR-ADM-05); it does not replace it."""
    warnings: list[str] = []
    if not entry_requirements:
        return warnings

    minimum = entry_requirements.get("min_certificate_grade")
    if minimum:
        min_rank = _rank(str(minimum))
        applicant_rank = _rank(previous_grade)
        if applicant_rank is None:
            warnings.append(
                f"Previous grade '{previous_grade or '(not given)'}' is not on the "
                f"recognised scale — verify manually against the {minimum} minimum."
            )
        elif min_rank is not None and applicant_rank > min_rank:
            warnings.append(
                f"Previous grade {previous_grade} is below the programme's minimum of {minimum}."
            )

    required_subjects = entry_requirements.get("required_subjects")
    if required_subjects:
        warnings.append(
            "Required subjects ("
            + ", ".join(required_subjects)
            + ") cannot be verified automatically — check the uploaded certificate."
        )

    return warnings


def meets_minimum_grade(entry_requirements: dict[str, Any], previous_grade: str) -> bool:
    """The one automatable check, used by merit-list ranking to flag (not
    exclude) applicants who fall short of the stated minimum."""
    minimum = entry_requirements.get("min_certificate_grade") if entry_requirements else None
    if not minimum:
        return True
    min_rank = _rank(str(minimum))
    applicant_rank = _rank(previous_grade)
    if min_rank is None or applicant_rank is None:
        return True  # unverifiable — not a basis for automatic exclusion
    return applicant_rank <= min_rank
