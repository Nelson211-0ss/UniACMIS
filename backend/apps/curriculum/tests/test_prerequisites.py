"""
Prerequisites and curriculum configuration (FR-CUR-02, FR-CUR-03).

A prerequisite cycle makes a programme impossible to complete, and is easy to
create accidentally across three separate edits — so it is rejected on save rather
than left to a reviewer to notice.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.curriculum.models import Course, CurriculumCourse, Prerequisite
from apps.curriculum.services import (
    curriculum_health,
    id_tokens_for_programme,
    unmet_prerequisites,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def courses(department):
    def make(code: str, credits: int = 3, level: int = 1) -> Course:
        return Course.objects.create(
            department=department, code=code, title=code, credit_hours=credits, level=level
        )

    return {code: make(code) for code in ("A101", "B101", "C101", "D101")}


# ------------------------------------------------------------------- cycles


def test_a_course_cannot_require_itself(courses):
    link = Prerequisite(course=courses["A101"], required_course=courses["A101"])
    with pytest.raises(ValidationError, match="cannot be its own prerequisite"):
        link.full_clean()


def test_self_reference_is_also_blocked_by_the_database(courses):
    """Defence in depth: the check constraint holds even for a raw insert that
    skips full_clean()."""
    with pytest.raises(IntegrityError), transaction.atomic():
        Prerequisite.objects.create(course=courses["A101"], required_course=courses["A101"])


def test_a_direct_cycle_is_rejected(courses):
    Prerequisite.objects.create(course=courses["B101"], required_course=courses["A101"])

    reverse = Prerequisite(course=courses["A101"], required_course=courses["B101"])
    with pytest.raises(ValidationError, match="cycle"):
        reverse.full_clean()


def test_an_indirect_cycle_is_rejected(courses):
    """A → B → C → A, built one edge at a time."""
    Prerequisite.objects.create(course=courses["B101"], required_course=courses["A101"])
    Prerequisite.objects.create(course=courses["C101"], required_course=courses["B101"])

    closing = Prerequisite(course=courses["A101"], required_course=courses["C101"])
    with pytest.raises(ValidationError, match="cycle"):
        closing.full_clean()


def test_a_legitimate_chain_is_allowed(courses):
    Prerequisite.objects.create(course=courses["B101"], required_course=courses["A101"])
    Prerequisite.objects.create(course=courses["C101"], required_course=courses["B101"])

    link = Prerequisite(course=courses["D101"], required_course=courses["C101"])
    link.full_clean()  # must not raise


def test_a_diamond_is_allowed(courses):
    """B and C both require A, and D requires both. Not a cycle."""
    Prerequisite.objects.create(course=courses["B101"], required_course=courses["A101"])
    Prerequisite.objects.create(course=courses["C101"], required_course=courses["A101"])
    Prerequisite.objects.create(course=courses["D101"], required_course=courses["B101"])

    link = Prerequisite(course=courses["D101"], required_course=courses["C101"])
    link.full_clean()


def test_the_same_pair_cannot_be_recorded_twice(courses):
    Prerequisite.objects.create(course=courses["B101"], required_course=courses["A101"])
    with pytest.raises(IntegrityError), transaction.atomic():
        Prerequisite.objects.create(course=courses["B101"], required_course=courses["A101"])


# -------------------------------------------------- prerequisite satisfaction


def test_no_prerequisites_means_nothing_unmet(courses):
    assert unmet_prerequisites([courses["A101"].pk], passed={}) == []


def test_a_missing_prerequisite_is_reported(courses):
    Prerequisite.objects.create(course=courses["B101"], required_course=courses["A101"])

    failures = unmet_prerequisites([courses["B101"].pk], passed={})
    assert len(failures) == 1
    assert failures[0].required_course_code == "A101"
    assert "has not been passed" in failures[0].reason


def test_a_passed_prerequisite_is_satisfied(courses):
    Prerequisite.objects.create(course=courses["B101"], required_course=courses["A101"])
    assert unmet_prerequisites([courses["B101"].pk], passed={courses["A101"].pk: None}) == []


def test_a_grade_threshold_is_enforced(courses):
    Prerequisite.objects.create(
        course=courses["B101"],
        required_course=courses["A101"],
        minimum_grade_point=Decimal("2.00"),
    )

    failures = unmet_prerequisites(
        [courses["B101"].pk], passed={courses["A101"].pk: Decimal("1.50")}
    )
    assert len(failures) == 1
    assert "at least 2.00" in failures[0].reason


def test_meeting_the_grade_threshold_satisfies_it(courses):
    Prerequisite.objects.create(
        course=courses["B101"],
        required_course=courses["A101"],
        minimum_grade_point=Decimal("2.00"),
    )
    assert (
        unmet_prerequisites([courses["B101"].pk], passed={courses["A101"].pk: Decimal("2.00")})
        == []
    )


def test_concurrent_registration_satisfies_only_where_allowed(courses):
    Prerequisite.objects.create(
        course=courses["B101"], required_course=courses["A101"], is_concurrent_allowed=True
    )
    Prerequisite.objects.create(
        course=courses["C101"], required_course=courses["A101"], is_concurrent_allowed=False
    )

    failures = unmet_prerequisites(
        [courses["B101"].pk, courses["C101"].pk],
        passed={},
        concurrent_ids=[courses["A101"].pk],
    )
    assert [f.course_code for f in failures] == ["C101"]


# ----------------------------------------------------- curriculum health


def test_a_curriculum_short_of_credits_is_flagged(curriculum_version, curriculum_course):
    report = curriculum_health(curriculum_version.pk)
    assert report["healthy"] is False
    assert any("short by" in problem for problem in report["problems"])


def test_an_empty_curriculum_is_flagged(curriculum_version):
    report = curriculum_health(curriculum_version.pk)
    assert report["healthy"] is False
    assert any("No courses" in problem for problem in report["problems"])


def test_a_complete_curriculum_is_healthy(curriculum_version, department):
    programme = curriculum_version.programme
    programme.total_credits_required = 12
    programme.duration_years = 1
    programme.save()

    for index in range(4):
        course = Course.objects.create(
            department=department,
            code=f"OK{index}",
            title=f"Course {index}",
            credit_hours=3,
            level=1,
        )
        CurriculumCourse.objects.create(
            curriculum_version=curriculum_version,
            course=course,
            year_of_study=1,
            semester_sequence=1,
        )

    report = curriculum_health(curriculum_version.pk)
    assert report["healthy"] is True, report["problems"]
    assert report["core_credits"] == 12


def test_a_course_beyond_the_programme_duration_is_rejected(curriculum_version, course):
    entry = CurriculumCourse(curriculum_version=curriculum_version, course=course, year_of_study=9)
    with pytest.raises(ValidationError, match="does not exist"):
        entry.full_clean()


def test_an_elective_needs_a_group_name(curriculum_version, course):
    entry = CurriculumCourse(
        curriculum_version=curriculum_version, course=course, year_of_study=1, is_core=False
    )
    with pytest.raises(ValidationError, match="group name"):
        entry.full_clean()


# ------------------------------------------------------- service boundary


def test_id_tokens_expose_codes_without_a_models_import(programme):
    """This is how `registry` builds a student ID without importing curriculum
    models (ARCHITECTURE §4)."""
    tokens = id_tokens_for_programme(programme.pk)
    assert tokens == {"faculty": "ENG", "programme": "CIV", "department": "CVE"}
