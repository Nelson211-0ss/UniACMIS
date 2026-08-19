"""Reporting service layer (FR-RPT-01…05)."""

from __future__ import annotations

import io
from decimal import Decimal

import pytest

from apps.enrollment.services import register_course
from apps.examinations import services as exam_services
from apps.reporting import services
from apps.reporting.models import DashboardWidget

pytestmark = pytest.mark.django_db


@pytest.fixture
def registration(student, course, semester, registrar):
    return register_course(
        student_id=student.pk, course_id=course.pk, semester_id=semester.pk, actor=registrar
    )


@pytest.fixture
def full_scheme(course):
    ca1 = exam_services.create_assessment(
        course_id=course.pk, name="CA1", weight_percent=Decimal("40"), max_score=Decimal("40")
    )
    final = exam_services.create_assessment(
        course_id=course.pk, name="Final", weight_percent=Decimal("60"), max_score=Decimal("100")
    )
    return ca1, final


# ------------------------------------------------------------------ dashboard


def test_dashboard_data_includes_only_enabled_widgets(student):
    DashboardWidget.objects.create(
        key="enrollment", label="Enrollment", is_enabled=True, sort_order=1
    )
    DashboardWidget.objects.create(key="ratios", label="Ratios", is_enabled=False, sort_order=2)

    data = services.dashboard_data()
    keys = [widget["key"] for widget in data]
    assert keys == ["enrollment"]
    assert data[0]["data"]["total"] == 1


def test_dashboard_ignores_a_widget_key_with_no_computed_report():
    DashboardWidget.objects.create(key="not_a_real_report", label="???", is_enabled=True)
    assert services.dashboard_data() == []


# ------------------------------------------------------------------ pass rate


def test_pass_rate_report_with_a_passing_and_a_failing_student(
    registration,
    full_scheme,
    grading_scale,
    programme,
    curriculum_version,
    academic_year,
    course,
    semester,
    registrar,
):
    from apps.registry.models import Gender
    from apps.registry.services import create_student

    ca1, final = full_scheme
    exam_services.record_mark(
        registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("40"), actor=None
    )
    exam_services.record_mark(
        registration_id=registration.pk, assessment_id=final.pk, score=Decimal("80"), actor=None
    )

    failing_student = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Failing",
        last_name="Student",
        gender=Gender.MALE,
        curriculum_version_id=curriculum_version.pk,
        reason="test",
    )
    failing_registration = register_course(
        student_id=failing_student.pk, course_id=course.pk, semester_id=semester.pk, actor=registrar
    )
    exam_services.record_mark(
        registration_id=failing_registration.pk,
        assessment_id=ca1.pk,
        score=Decimal("5"),
        actor=None,
    )
    exam_services.record_mark(
        registration_id=failing_registration.pk,
        assessment_id=final.pk,
        score=Decimal("10"),
        actor=None,
    )

    report = services.pass_rate_report(course_id=course.pk, semester_id=semester.pk)
    assert report["passed"] == 1
    assert report["failed"] == 1
    assert report["incomplete"] == 0
    assert report["pass_rate_percent"] == 50.0


def test_pass_rate_report_excludes_incomplete_registrations_from_the_rate(
    registration, full_scheme
):
    ca1, _final = full_scheme
    exam_services.record_mark(
        registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("40"), actor=None
    )

    report = services.pass_rate_report(
        course_id=registration.course_id, semester_id=registration.semester_id
    )
    assert report["incomplete"] == 1
    assert report["passed"] == 0
    assert report["pass_rate_percent"] is None


# ------------------------------------------------------------------- exports


def test_the_student_register_report_is_exportable(student):
    rows = services.report_rows("student_register", {})
    assert len(rows) == 1
    assert rows[0]["student_number"] == student.student_id


def test_pass_rate_export_requires_course_and_semester():
    with pytest.raises(services.MissingReportParameter):
        services.report_rows("pass_rate", {})


def test_an_unknown_report_key_is_rejected():
    with pytest.raises(services.UnknownReport):
        services.report_rows("not-a-real-report", {})


def test_rows_to_csv_round_trips_headers_and_values():
    csv_text = services.rows_to_csv([{"a": "1", "b": "2"}, {"a": "3", "b": "4"}])
    lines = csv_text.strip().splitlines()
    assert lines[0] == "a,b"
    assert lines[1] == "1,2"


def test_rows_to_csv_handles_no_rows():
    assert services.rows_to_csv([]) == ""


def test_rows_to_xlsx_produces_a_real_workbook():
    from openpyxl import load_workbook

    content = services.rows_to_xlsx([{"a": 1, "b": 2}])
    workbook = load_workbook(filename=io.BytesIO(content))
    sheet = workbook.active
    assert [cell.value for cell in sheet[1]] == ["a", "b"]
    assert [cell.value for cell in sheet[2]] == ["1", "2"]
