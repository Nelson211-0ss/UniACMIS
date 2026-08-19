"""Entry-requirement screening (FR-ADM-03)."""

from __future__ import annotations

from apps.admissions.eligibility import evaluate_entry_requirements, meets_minimum_grade


def test_no_requirements_means_no_warnings():
    assert evaluate_entry_requirements({}, "F") == []


def test_meeting_the_minimum_grade_is_silent():
    assert evaluate_entry_requirements({"min_certificate_grade": "C"}, "B") == []


def test_exactly_the_minimum_grade_is_silent():
    assert evaluate_entry_requirements({"min_certificate_grade": "C"}, "C") == []


def test_below_the_minimum_grade_warns():
    warnings = evaluate_entry_requirements({"min_certificate_grade": "C"}, "D")
    assert len(warnings) == 1
    assert "below the programme's minimum" in warnings[0]


def test_an_unrecognised_grade_is_flagged_for_manual_review_not_rejected():
    """A foreign qualification on an unfamiliar scale needs a human, not an
    automatic fail."""
    warnings = evaluate_entry_requirements({"min_certificate_grade": "C"}, "IB-38")
    assert len(warnings) == 1
    assert "verify manually" in warnings[0]


def test_a_missing_grade_is_also_flagged_not_silently_passed():
    warnings = evaluate_entry_requirements({"min_certificate_grade": "C"}, "")
    assert len(warnings) == 1
    assert "not given" in warnings[0]


def test_required_subjects_are_noted_for_manual_verification():
    warnings = evaluate_entry_requirements({"required_subjects": ["Mathematics", "English"]}, "A")
    assert len(warnings) == 1
    assert "Mathematics" in warnings[0] and "English" in warnings[0]


def test_both_checks_can_fire_together():
    warnings = evaluate_entry_requirements(
        {"min_certificate_grade": "B", "required_subjects": ["Physics"]}, "D"
    )
    assert len(warnings) == 2


def test_meets_minimum_grade_boolean_matches_the_warning():
    assert meets_minimum_grade({"min_certificate_grade": "C"}, "B") is True
    assert meets_minimum_grade({"min_certificate_grade": "C"}, "D") is False


def test_meets_minimum_grade_is_permissive_with_no_rule():
    assert meets_minimum_grade({}, "F") is True


def test_meets_minimum_grade_is_permissive_when_unverifiable():
    assert meets_minimum_grade({"min_certificate_grade": "C"}, "unrecognised") is True
