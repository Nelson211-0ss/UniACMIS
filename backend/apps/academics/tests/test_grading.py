"""
Grading and GPA computation (FR-EXM-04).

These are the arithmetic that decides degree classifications, so the boundaries
are tested exhaustively rather than sampled.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.academics.models import GradeBand, GradingScale
from apps.academics.services.grading import (
    CourseGrade,
    GradingConfigurationError,
    cgpa,
    classification,
    gpa,
    grade_for,
)

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------- grade_for()


@pytest.mark.parametrize(
    ("percent", "letter", "points"),
    [
        # Every band boundary, on both sides.
        ("100.00", "A", "4.00"),
        ("70.00", "A", "4.00"),
        ("69.99", "B+", "3.50"),
        ("65.00", "B+", "3.50"),
        ("64.99", "B", "3.00"),
        ("60.00", "B", "3.00"),
        ("59.99", "C+", "2.50"),
        ("55.00", "C+", "2.50"),
        ("54.99", "C", "2.00"),
        ("50.00", "C", "2.00"),
        ("49.99", "D+", "1.50"),
        ("45.00", "D+", "1.50"),
        ("44.99", "D", "1.00"),
        ("40.00", "D", "1.00"),
        ("39.99", "F", "0.00"),
        ("0.00", "F", "0.00"),
    ],
)
def test_grade_for_band_boundaries(grading_scale, percent, letter, points):
    result = grade_for(Decimal(percent), grading_scale)
    assert result.letter == letter
    assert result.grade_point == Decimal(points)


def test_grade_for_marks_pass_and_fail(grading_scale):
    assert grade_for(Decimal("50.00"), grading_scale).is_pass is True
    assert grade_for(Decimal("49.99"), grading_scale).is_pass is False


@pytest.mark.parametrize("percent", ["-0.01", "100.01", "150"])
def test_grade_for_rejects_out_of_range(grading_scale, percent):
    with pytest.raises(GradingConfigurationError):
        grade_for(Decimal(percent), grading_scale)


def test_grade_for_raises_when_no_scale_configured(db):
    with pytest.raises(GradingConfigurationError, match="No grading scale is configured"):
        grade_for(Decimal("55"))


def test_grade_for_raises_on_gap_rather_than_silently_failing(db):
    """A mark that falls into a gap must surface the misconfiguration.

    Returning F would hide a broken scale until a student appealed.
    """
    scale = GradingScale.objects.create(name="Holed", max_grade_point=Decimal("4.00"))
    GradeBand.objects.create(
        scale=scale,
        letter="A",
        min_percent=Decimal("60.00"),
        max_percent=Decimal("100.00"),
        grade_point=Decimal("4.00"),
    )
    GradeBand.objects.create(
        scale=scale,
        letter="F",
        min_percent=Decimal("0.00"),
        max_percent=Decimal("40.00"),
        grade_point=Decimal("0.00"),
    )

    with pytest.raises(GradingConfigurationError, match="gap"):
        grade_for(Decimal("50.00"), scale)


# ---------------------------------------------------- band coverage validation


def test_valid_scale_passes_validation(grading_scale):
    grading_scale.validate_bands()  # must not raise


def test_validation_rejects_a_gap(db):
    scale = GradingScale.objects.create(name="Gapped", max_grade_point=Decimal("4.00"))
    bands = [
        GradeBand(
            scale=scale,
            letter="A",
            min_percent=Decimal("60.00"),
            max_percent=Decimal("100.00"),
            grade_point=Decimal("4.00"),
        ),
        GradeBand(
            scale=scale,
            letter="F",
            min_percent=Decimal("0.00"),
            max_percent=Decimal("50.00"),
            grade_point=Decimal("0.00"),
        ),
    ]
    with pytest.raises(ValidationError, match="fall into no band"):
        scale.validate_bands(bands)


def test_validation_rejects_an_overlap(db):
    scale = GradingScale.objects.create(name="Overlapping", max_grade_point=Decimal("4.00"))
    bands = [
        GradeBand(
            scale=scale,
            letter="A",
            min_percent=Decimal("50.00"),
            max_percent=Decimal("100.00"),
            grade_point=Decimal("4.00"),
        ),
        GradeBand(
            scale=scale,
            letter="F",
            min_percent=Decimal("0.00"),
            max_percent=Decimal("60.00"),
            grade_point=Decimal("0.00"),
        ),
    ]
    with pytest.raises(ValidationError, match="overlap"):
        scale.validate_bands(bands)


def test_validation_requires_coverage_to_zero(db):
    scale = GradingScale.objects.create(name="Truncated", max_grade_point=Decimal("4.00"))
    bands = [
        GradeBand(
            scale=scale,
            letter="A",
            min_percent=Decimal("40.00"),
            max_percent=Decimal("100.00"),
            grade_point=Decimal("4.00"),
        )
    ]
    with pytest.raises(ValidationError, match="must start at 0"):
        scale.validate_bands(bands)


def test_validation_requires_coverage_to_hundred(db):
    scale = GradingScale.objects.create(name="Capped", max_grade_point=Decimal("4.00"))
    bands = [
        GradeBand(
            scale=scale,
            letter="F",
            min_percent=Decimal("0.00"),
            max_percent=Decimal("90.00"),
            grade_point=Decimal("0.00"),
        )
    ]
    with pytest.raises(ValidationError, match="must reach 100"):
        scale.validate_bands(bands)


def test_validation_rejects_grade_point_above_scale_maximum(db):
    scale = GradingScale.objects.create(name="Too high", max_grade_point=Decimal("4.00"))
    bands = [
        GradeBand(
            scale=scale,
            letter="A",
            min_percent=Decimal("0.00"),
            max_percent=Decimal("100.00"),
            grade_point=Decimal("5.00"),
        )
    ]
    with pytest.raises(ValidationError, match="above the scale maximum"):
        scale.validate_bands(bands)


def test_validation_rejects_empty_scale(db):
    scale = GradingScale.objects.create(name="Empty", max_grade_point=Decimal("4.00"))
    with pytest.raises(ValidationError, match="at least one band"):
        scale.validate_bands()


# ---------------------------------------------------------------------- gpa()


def test_gpa_is_credit_weighted():
    # 4 credits at 4.00 and 2 credits at 1.00 → (16 + 2) / 6 = 3.00
    assert gpa([(4, Decimal("4.00")), (2, Decimal("1.00"))]) == Decimal("3.00")


def test_gpa_weights_by_credits_not_by_course_count():
    """A 6-credit fail must outweigh a 1-credit distinction."""
    unweighted_mean = Decimal("2.00")  # what a naive average would give
    result = gpa([(6, Decimal("0.00")), (1, Decimal("4.00"))])
    assert result is not None
    assert result < unweighted_mean
    assert result == Decimal("0.57")


def test_gpa_returns_none_when_nothing_is_graded():
    """None, not 0.00 — a new student has no GPA, they have not failed."""
    assert gpa([]) is None


def test_gpa_ignores_zero_credit_courses():
    assert gpa([(0, Decimal("0.00")), (3, Decimal("4.00"))]) == Decimal("4.00")


def test_gpa_of_only_zero_credit_courses_is_none():
    assert gpa([(0, Decimal("4.00"))]) is None


def test_gpa_rounds_half_up():
    # (3 × 2.995) / 3 = 2.995 → 3.00, not 2.99
    assert gpa([(3, Decimal("2.995"))]) == Decimal("3.00")


def test_gpa_accepts_course_grade_objects():
    entries = [
        CourseGrade(credit_hours=3, grade_point=Decimal("4.00")),
        CourseGrade(credit_hours=3, grade_point=Decimal("2.00")),
    ]
    assert gpa(entries) == Decimal("3.00")


def test_gpa_excludes_entries_flagged_out_of_gpa():
    """Audited or transferred credit that should not affect the average."""
    entries = [
        CourseGrade(credit_hours=3, grade_point=Decimal("4.00")),
        CourseGrade(credit_hours=3, grade_point=Decimal("0.00"), counts_toward_gpa=False),
    ]
    assert gpa(entries) == Decimal("4.00")


def test_cgpa_matches_gpa_over_the_cumulative_set():
    semester_one = [(4, Decimal("4.00")), (2, Decimal("3.00"))]
    semester_two = [(3, Decimal("2.00"))]
    assert cgpa(semester_one + semester_two) == gpa(semester_one + semester_two)


def test_cgpa_from_semester_summaries_matches_course_level():
    """Equivalent whether computed from courses or from per-semester totals —
    which is what makes transfer credit (FR-REG-05) consistent."""
    courses = [(4, Decimal("4.00")), (2, Decimal("1.00")), (6, Decimal("3.00"))]
    from apps.academics.services.grading import weighted_semester_cgpa

    semester_summaries = [(6, gpa(courses[:2])), (6, Decimal("3.00"))]
    assert weighted_semester_cgpa(semester_summaries) == cgpa(courses)


# ------------------------------------------------------------- classification


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("4.00", "First Class"),
        ("3.50", "First Class"),
        ("3.49", "Second Class (Upper Division)"),
        ("3.00", "Second Class (Upper Division)"),
        ("2.50", "Second Class (Lower Division)"),
        ("2.00", "Pass"),
        ("1.99", "Fail"),
    ],
)
def test_classification_on_a_four_point_scale(grading_scale, value, expected):
    assert classification(Decimal(value), grading_scale) == expected


def test_classification_scales_with_the_configured_maximum(db):
    """A 5.00-point institution must not be judged against 4.00 thresholds."""
    scale = GradingScale.objects.create(name="Five point", max_grade_point=Decimal("5.00"))
    assert classification(Decimal("4.40"), scale) == "First Class"
    assert classification(Decimal("3.50"), scale) == "Second Class (Lower Division)"


def test_classification_of_none_is_blank(grading_scale):
    assert classification(None, grading_scale) == ""
