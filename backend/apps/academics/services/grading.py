"""
Grade and GPA computation (FR-EXM-04).

Pure functions over values, with no ORM access beyond an optional scale lookup, so
they can be unit-tested exhaustively and reused by `examinations` in Phase 3
without dragging assessment models into the calculation.

Rounding is explicit `ROUND_HALF_UP` at two decimal places. Left to float
arithmetic, a 2.995 GPA would sometimes present as 2.99 and sometimes as 3.00 —
and on a transcript that difference decides degree classifications.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from apps.academics.models import GradeBand, GradingScale

TWO_PLACES = Decimal("0.01")


class GradingConfigurationError(Exception):
    """The configured scale cannot grade the given mark."""


@dataclass(frozen=True)
class GradeResult:
    letter: str
    grade_point: Decimal
    is_pass: bool
    description: str = ""


@dataclass(frozen=True)
class CourseGrade:
    """One graded course, as GPA computation needs it."""

    credit_hours: int
    grade_point: Decimal
    counts_toward_gpa: bool = True


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _as_decimal(value: Decimal | float | int | str) -> Decimal:
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise GradingConfigurationError(f"{value!r} is not a valid number.") from exc


def grade_for(
    percent: Decimal | float | int | str,
    scale: GradingScale | None = None,
    bands: Sequence[GradeBand] | None = None,
) -> GradeResult:
    """Map a percentage to its band.

    Raises rather than silently returning a fail when no band matches: an
    unmatched mark means the scale is misconfigured, and quietly grading it F
    would hide that from everyone until a student appealed.
    """
    value = _as_decimal(percent)

    if value < 0 or value > 100:
        raise GradingConfigurationError(f"A percentage of {value} is outside 0–100.")

    if bands is None:
        scale = scale or GradingScale.get_default()
        if scale is None:
            raise GradingConfigurationError(
                "No grading scale is configured. Set one up before entering marks."
            )
        bands = list(scale.bands.all())

    for band in bands:
        if band.contains(value):
            return GradeResult(
                letter=band.letter,
                grade_point=band.grade_point,
                is_pass=band.is_pass,
                description=band.description,
            )

    raise GradingConfigurationError(
        f"No grade band covers {value}%. The grading scale has a gap — fix it "
        "before publishing any result computed with it."
    )


def gpa(entries: Iterable[CourseGrade | tuple[int, Decimal]]) -> Decimal | None:
    """Credit-weighted grade point average.

        Σ(credit_hours × grade_point) / Σ(credit_hours)

    Returns None when there is nothing to average — distinct from 0.00, which
    would mean the student failed everything. A new student's transcript must not
    show a 0.00 GPA before they have sat anything.
    """
    total_points = Decimal("0")
    total_credits = Decimal("0")

    for entry in entries:
        if isinstance(entry, CourseGrade):
            if not entry.counts_toward_gpa:
                continue
            credits = _as_decimal(entry.credit_hours)
            points = _as_decimal(entry.grade_point)
        else:
            credits = _as_decimal(entry[0])
            points = _as_decimal(entry[1])

        if credits <= 0:
            # A zero-credit course cannot move an average; counting it as if it
            # had weight would distort every GPA that included one.
            continue

        total_points += credits * points
        total_credits += credits

    if total_credits == 0:
        return None

    return _quantize(total_points / total_credits)


def cgpa(entries: Iterable[CourseGrade | tuple[int, Decimal]]) -> Decimal | None:
    """Cumulative GPA — the same credit-weighted computation over every attempt
    that counts.

    *Which* attempts count (a retake replacing a fail, a carry-over counting
    twice) is academic policy owned by `examinations` (FR-ENR-05), not arithmetic.
    This function grades whatever set it is handed, which keeps the policy
    reviewable in one place instead of buried in a formula.
    """
    return gpa(entries)


def weighted_semester_cgpa(
    semesters: Iterable[tuple[int, Decimal]],
) -> Decimal | None:
    """CGPA from per-semester (total_credits, gpa) pairs.

    Mathematically equivalent to `cgpa()` over the underlying courses, and useful
    when only the summaries survive — for a transfer student whose previous
    institution supplied totals rather than a full course list (FR-REG-05).
    """
    return gpa(semesters)


def classification(value: Decimal | None, scale: GradingScale | None = None) -> str:
    """Degree classification band for a CGPA.

    Deliberately derived from the configured scale's maximum rather than from
    hard-coded 4.00 thresholds, so a 5.00-point institution gets sensible answers.
    The exact wording is an institutional policy question flagged in the SRS open
    items, so this is a documented default rather than a claim about any
    particular university's regulations.
    """
    if value is None:
        return ""

    scale = scale or GradingScale.get_default()
    maximum = scale.max_grade_point if scale else Decimal("4.00")
    if maximum <= 0:
        return ""

    ratio = value / maximum

    if ratio >= Decimal("0.875"):
        return "First Class"
    if ratio >= Decimal("0.750"):
        return "Second Class (Upper Division)"
    if ratio >= Decimal("0.625"):
        return "Second Class (Lower Division)"
    if ratio >= Decimal("0.500"):
        return "Pass"
    return "Fail"
