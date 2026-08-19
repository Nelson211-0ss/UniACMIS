"""Bulk legacy student import (NFR-DATA-03)."""

from __future__ import annotations

import pytest

from apps.registry.models import Student
from apps.registry.services import import_students

pytestmark = pytest.mark.django_db


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "first_name": "Legacy",
        "last_name": "Student",
        "gender": "female",
        "programme_code": "CIV",
        "entry_academic_year": "2026/2027",
    }
    row.update(overrides)
    return row


def test_a_dry_run_validates_but_writes_nothing(programme, academic_year):
    result = import_students([_row()], commit=False)
    assert result == {"total": 1, "valid": 1, "created": 0, "errors": []}
    assert Student.objects.count() == 0


def test_committing_a_valid_batch_creates_every_row(programme, academic_year):
    rows = [_row(first_name="First"), _row(first_name="Second")]
    result = import_students(rows, commit=True)
    assert result["created"] == 2
    assert Student.objects.count() == 2


def test_an_unknown_programme_code_is_reported_by_row_number(programme, academic_year):
    rows = [_row(), _row(programme_code="NOPE")]
    result = import_students(rows, commit=False)
    assert result["errors"] == [
        {"row": 2, "errors": {"programme_code": "No programme with code 'NOPE'."}}
    ]


def test_an_unknown_academic_year_is_rejected(programme, academic_year):
    result = import_students([_row(entry_academic_year="1999/2000")], commit=False)
    assert "entry_academic_year" in result["errors"][0]["errors"]


def test_a_missing_required_field_is_rejected(programme, academic_year):
    result = import_students([_row(first_name="")], commit=False)
    assert "first_name" in result["errors"][0]["errors"]


def test_one_invalid_row_blocks_the_whole_commit(programme, academic_year):
    rows = [_row(first_name="Good"), _row(gender="not-a-real-gender")]
    result = import_students(rows, commit=True)
    assert result["created"] == 0
    assert Student.objects.count() == 0
    assert len(result["errors"]) == 1
    assert result["errors"][0]["row"] == 2


def test_a_supplied_student_id_is_used_instead_of_generating_one(programme, academic_year):
    result = import_students([_row(student_id="LEGACY/0001")], commit=True)
    assert result["created"] == 1
    student = Student.objects.get()
    assert student.student_id == "LEGACY/0001"


def test_duplicate_supplied_student_ids_in_one_batch_are_rejected(programme, academic_year):
    rows = [_row(student_id="LEGACY/0001"), _row(student_id="LEGACY/0001", first_name="Other")]
    result = import_students(rows, commit=False)
    assert len(result["errors"]) == 1
    assert result["errors"][0]["row"] == 2


def test_disability_without_details_is_rejected(programme, academic_year):
    result = import_students([_row(has_disability="true")], commit=False)
    assert "disability_details" in result["errors"][0]["errors"]


def test_disability_with_details_is_accepted(programme, academic_year):
    result = import_students(
        [_row(has_disability="true", disability_details="Wheelchair user")], commit=True
    )
    assert result["created"] == 1
    student = Student.objects.get()
    assert student.has_disability is True


def test_a_curriculum_version_for_a_different_programme_is_rejected(
    programme, academic_year, department
):
    from apps.curriculum.models import Award, CurriculumStatus, CurriculumVersion, Programme

    other_programme = Programme.objects.create(
        department=department,
        code="OTH",
        name="Other Programme",
        award=Award.BACHELOR,
        duration_years=4,
        total_credits_required=120,
        min_credits_per_semester=12,
        max_credits_per_semester=24,
    )
    CurriculumVersion.objects.create(
        programme=other_programme,
        version="2026-v1",
        status=CurriculumStatus.ACTIVE,
        effective_from=academic_year,
    )
    result = import_students([_row(curriculum_version="2026-v1")], commit=False)
    assert "curriculum_version" in result["errors"][0]["errors"]
