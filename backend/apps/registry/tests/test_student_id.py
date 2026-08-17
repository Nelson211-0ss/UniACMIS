"""
Student ID generation (FR-REG-01): unique, non-reusable, template-driven.
"""

from __future__ import annotations

import threading

import pytest
from django.db import connection

from apps.academics.models import Institution
from apps.core.models import IdSequence
from apps.registry.id_generation import IdTemplateError, generate_student_id, sequence_scope
from apps.registry.models import Gender, Student
from apps.registry.services import create_student

pytestmark = pytest.mark.django_db


def test_id_follows_the_configured_template(institution, programme, academic_year):
    student_id = generate_student_id(programme.pk, academic_year.name)
    assert student_id == "ENG/CIV/2026/0001"


def test_sequence_advances_per_scope(institution, programme, academic_year):
    first = generate_student_id(programme.pk, academic_year.name)
    second = generate_student_id(programme.pk, academic_year.name)
    assert first.endswith("0001")
    assert second.endswith("0002")


def test_the_academic_year_contributes_its_leading_year(institution, programme):
    from datetime import date

    from apps.academics.models import AcademicYear

    year = AcademicYear.objects.create(
        name="2030/2031", start_date=date(2030, 9, 1), end_date=date(2031, 7, 31)
    )
    assert "/2030/" in generate_student_id(programme.pk, year.name)


def test_counters_are_scoped_per_programme_and_year(
    institution, programme, department, academic_year
):
    from apps.curriculum.models import Award, Programme

    other = Programme.objects.create(
        department=department,
        code="ELE",
        name="BSc Electrical Engineering",
        award=Award.BACHELOR,
        duration_years=5,
    )

    assert generate_student_id(programme.pk, academic_year.name).endswith("0001")
    # A different programme starts its own count rather than continuing the first.
    assert generate_student_id(other.pk, academic_year.name).endswith("0001")
    assert generate_student_id(programme.pk, academic_year.name).endswith("0002")


def test_a_custom_template_is_honoured(institution, programme, academic_year):
    institution.student_id_template = "{year}-{programme}-{seq:05d}"
    institution.save()
    assert generate_student_id(programme.pk, academic_year.name) == "2026-CIV-00001"


def test_an_unknown_placeholder_is_reported_clearly(institution, programme, academic_year):
    institution.student_id_template = "{campus}/{year}/{seq:04d}"
    institution.save()
    with pytest.raises(IdTemplateError, match="not a known placeholder"):
        generate_student_id(programme.pk, academic_year.name)


def test_a_template_without_a_sequence_is_rejected_at_configuration_time(institution):
    from django.core.exceptions import ValidationError

    institution.student_id_template = "{faculty}/{year}"
    with pytest.raises(ValidationError):
        institution.full_clean()


def test_falls_back_when_the_template_is_blank(institution, programme, academic_year):
    """A cleared template must not stop admissions: fall back to the documented
    default rather than raising in the middle of a registrar's data entry."""
    institution.student_id_template = ""
    institution.save(update_fields=["student_id_template"])

    assert generate_student_id(programme.pk, academic_year.name) == "ENG/CIV/2026/0001"


def test_the_template_helper_falls_back_with_no_institution_row(db):
    """Before setup has run at all there is no Institution; configuration reads
    still have to answer."""
    from apps.academics.services import config

    assert not Institution.objects.exists()
    assert config.student_id_template() == config.DEFAULT_STUDENT_ID_TEMPLATE
    assert config.attendance_threshold() == config.DEFAULT_ATTENDANCE_THRESHOLD


def test_created_students_get_distinct_ids(institution, programme, academic_year):
    ids = {
        create_student(
            programme_id=programme.pk,
            entry_academic_year_id=academic_year.pk,
            first_name=f"Student{n}",
            last_name="Test",
            gender=Gender.FEMALE,
            reason="test",
        ).student_id
        for n in range(5)
    }
    assert len(ids) == 5


def test_an_explicit_id_is_accepted_for_legacy_migration(institution, programme, academic_year):
    student = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Legacy",
        last_name="Record",
        gender=Gender.MALE,
        student_id="OLD/2019/0042",
        reason="migrated",
    )
    assert student.student_id == "OLD/2019/0042"
    # The generator's counter is untouched by a supplied ID.
    assert IdSequence.peek(sequence_scope("ENG", "CIV", "2026")) == 0


def test_ids_are_not_reused_after_a_student_is_removed(institution, programme, academic_year):
    """Soft delete plus a monotonic counter is what keeps a withdrawn student's
    number retired."""
    first = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Gone",
        last_name="Student",
        gender=Gender.MALE,
        reason="test",
    )
    original_id = first.student_id
    first.delete()

    second = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="New",
        last_name="Student",
        gender=Gender.FEMALE,
        reason="test",
    )

    assert second.student_id != original_id
    # The deleted record still occupies the number.
    assert Student.all_objects.filter(student_id=original_id).exists()
    assert not Student.objects.filter(student_id=original_id).exists()


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_concurrent_admissions_never_collide(institution, programme, academic_year):
    """Six clerks admitting into the same programme at the same moment.

    This is the failure that matters: a duplicate student ID is printed on a
    certificate before anyone notices.
    """
    results: list[str] = []
    errors: list[Exception] = []
    lock = threading.Lock()
    start = threading.Barrier(6)

    def worker(index: int) -> None:
        try:
            start.wait(timeout=10)
            student = create_student(
                programme_id=programme.pk,
                entry_academic_year_id=academic_year.pk,
                first_name=f"Concurrent{index}",
                last_name="Admission",
                gender=Gender.FEMALE,
                reason="concurrency test",
            )
            with lock:
                results.append(student.student_id)
        except Exception as exc:  # pragma: no cover
            with lock:
                errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, f"threads raised: {errors}"
    assert len(results) == 6
    assert len(set(results)) == 6, f"duplicate student IDs: {sorted(results)}"
