"""
Examinations API: the exam office owns the scheme and the mark; a lecturer
enters marks for their own department; a student sees only their own result,
and only once Senate has approved it and the office has published it
(FR-EXM-01…08).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.enrollment.services import register_course
from apps.examinations import services

pytestmark = pytest.mark.django_db

ASSESSMENTS_URL = "/api/v1/examinations/assessments/"
MARKS_URL = "/api/v1/examinations/marks/"
APPEALS_URL = "/api/v1/examinations/appeals/"
APPROVALS_URL = "/api/v1/examinations/approvals/"


@pytest.fixture
def registration(student_portal_user, student, course, semester, registrar):
    return register_course(
        student_id=student.pk, course_id=course.pk, semester_id=semester.pk, actor=registrar
    )


@pytest.fixture
def assessment(course):
    return services.create_assessment(
        course_id=course.pk, name="CA1", weight_percent=Decimal("100"), max_score=Decimal("100")
    )


@pytest.mark.integration
def test_the_examinations_office_can_create_an_assessment(examinations_officer, as_user, course):
    response = as_user(examinations_officer).post(
        ASSESSMENTS_URL,
        {"course": course.pk, "name": "CA1", "weight_percent": "40.00", "max_score": "40.00"},
        format="json",
    )
    assert response.status_code == 201


@pytest.mark.integration
def test_a_lecturer_cannot_create_an_assessment(lecturer, as_user, course):
    response = as_user(lecturer).post(
        ASSESSMENTS_URL,
        {"course": course.pk, "name": "CA1", "weight_percent": "40.00"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_a_lecturer_can_view_assessments(lecturer, as_user, assessment):
    response = as_user(lecturer).get(ASSESSMENTS_URL)
    assert response.status_code == 200


@pytest.mark.integration
def test_a_lecturer_can_record_a_mark(lecturer, as_user, registration, assessment):
    response = as_user(lecturer).post(
        f"{MARKS_URL}record/",
        {"registration": registration.pk, "assessment": assessment.pk, "score": "85.00"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["score"] == "85.00"


@pytest.mark.integration
def test_a_student_cannot_record_a_mark(student_portal_user, as_user, registration, assessment):
    response = as_user(student_portal_user).post(
        f"{MARKS_URL}record/",
        {"registration": registration.pk, "assessment": assessment.pk, "score": "85.00"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_a_student_sees_only_their_own_marks(
    lecturer, as_user, student_portal_user, registration, assessment
):
    as_user(lecturer).post(
        f"{MARKS_URL}record/",
        {"registration": registration.pk, "assessment": assessment.pk, "score": "85.00"},
        format="json",
    )
    response = as_user(student_portal_user).get(MARKS_URL)
    assert response.status_code == 200
    assert len(response.data["results"]) == 1


@pytest.mark.integration
def test_a_hod_can_moderate_a_mark(hod, as_user, lecturer, registration, assessment):
    as_user(lecturer).post(
        f"{MARKS_URL}record/",
        {"registration": registration.pk, "assessment": assessment.pk, "score": "60.00"},
        format="json",
    )
    mark_id = services.record_mark(
        registration_id=registration.pk,
        assessment_id=assessment.pk,
        score=Decimal("60"),
        actor=None,
    ).pk
    response = as_user(hod).post(
        f"{MARKS_URL}{mark_id}/moderate/",
        {"moderated_score": "65.00", "notes": "Re-checked against the marking scheme"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["moderated_score"] == "65.00"


@pytest.mark.integration
def test_a_lecturer_cannot_moderate_a_mark(lecturer, as_user, registration, assessment):
    mark = services.record_mark(
        registration_id=registration.pk,
        assessment_id=assessment.pk,
        score=Decimal("60"),
        actor=None,
    )
    response = as_user(lecturer).post(
        f"{MARKS_URL}{mark.pk}/moderate/",
        {"moderated_score": "65.00", "notes": "Trying to self-moderate"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_the_examinations_office_can_flag_and_clear_an_irregularity(
    examinations_officer, as_user, registration, assessment
):
    mark = services.record_mark(
        registration_id=registration.pk,
        assessment_id=assessment.pk,
        score=Decimal("60"),
        actor=None,
    )
    flagged = as_user(examinations_officer).post(
        f"{MARKS_URL}{mark.pk}/flag-irregularity/",
        {"notes": "Suspected impersonation"},
        format="json",
    )
    assert flagged.status_code == 200
    assert flagged.data["is_irregular"] is True

    cleared = as_user(examinations_officer).post(
        f"{MARKS_URL}{mark.pk}/clear-irregularity/", format="json"
    )
    assert cleared.status_code == 200
    assert cleared.data["is_irregular"] is False


@pytest.mark.integration
def test_the_course_result_endpoint(examinations_officer, as_user, registration, assessment):
    services.record_mark(
        registration_id=registration.pk,
        assessment_id=assessment.pk,
        score=Decimal("85"),
        actor=None,
    )
    response = as_user(examinations_officer).get(
        f"/api/v1/examinations/registrations/{registration.pk}/result/"
    )
    assert response.status_code == 200
    assert response.data["percent"] == "85.00"


@pytest.mark.integration
def test_a_student_can_submit_an_appeal(student_portal_user, as_user, registration, assessment):
    response = as_user(student_portal_user).post(
        APPEALS_URL,
        {
            "registration": registration.pk,
            "assessment": assessment.pk,
            "reason": "Question 3 was marked incorrectly",
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["status"] == "submitted"


@pytest.mark.integration
def test_a_lecturer_cannot_decide_an_appeal(lecturer, as_user, hod, registration, assessment):
    appeal = services.submit_appeal(
        registration_id=registration.pk,
        assessment_id=assessment.pk,
        reason="Disputed mark",
        actor=None,
    )
    response = as_user(lecturer).post(
        f"{APPEALS_URL}{appeal.pk}/decide/",
        {"decision": "upheld", "notes": "Trying to self-approve"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_a_hod_can_decide_an_appeal(hod, as_user, registration, assessment):
    appeal = services.submit_appeal(
        registration_id=registration.pk,
        assessment_id=assessment.pk,
        reason="Disputed mark",
        actor=None,
    )
    response = as_user(hod).post(
        f"{APPEALS_URL}{appeal.pk}/decide/",
        {"decision": "rejected", "notes": "Mark confirmed correct on review"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["status"] == "rejected"


@pytest.mark.integration
def test_the_full_approval_workflow(examinations_officer, senate_member, as_user, semester):
    submit = as_user(examinations_officer).post(
        APPROVALS_URL, {"semester": semester.pk}, format="json"
    )
    assert submit.status_code == 201
    approval_id = submit.data["id"]

    denied = as_user(examinations_officer).post(
        f"{APPROVALS_URL}{approval_id}/approve/", format="json"
    )
    assert denied.status_code == 403

    approved = as_user(senate_member).post(f"{APPROVALS_URL}{approval_id}/approve/", format="json")
    assert approved.status_code == 200
    assert approved.data["status"] == "approved"

    published = as_user(examinations_officer).post(
        f"{APPROVALS_URL}{approval_id}/publish/", format="json"
    )
    assert published.status_code == 200
    assert published.data["status"] == "published"


@pytest.mark.integration
def test_senate_cannot_publish_directly(examinations_officer, senate_member, as_user, semester):
    submit = as_user(examinations_officer).post(
        APPROVALS_URL, {"semester": semester.pk}, format="json"
    )
    approval_id = submit.data["id"]
    as_user(senate_member).post(f"{APPROVALS_URL}{approval_id}/approve/", format="json")

    response = as_user(senate_member).post(f"{APPROVALS_URL}{approval_id}/publish/", format="json")
    assert response.status_code == 403


@pytest.mark.integration
def test_a_student_can_see_their_own_result_once_published(
    student_portal_user,
    examinations_officer,
    senate_member,
    as_user,
    registration,
    assessment,
    student,
    semester,
    grading_scale,
):
    services.record_mark(
        registration_id=registration.pk,
        assessment_id=assessment.pk,
        score=Decimal("85"),
        actor=None,
    )
    submit = as_user(examinations_officer).post(
        APPROVALS_URL, {"semester": semester.pk}, format="json"
    )
    approval_id = submit.data["id"]
    as_user(senate_member).post(f"{APPROVALS_URL}{approval_id}/approve/", format="json")
    as_user(examinations_officer).post(f"{APPROVALS_URL}{approval_id}/publish/", format="json")

    response = as_user(student_portal_user).get(
        f"/api/v1/examinations/students/{student.pk}/semesters/{semester.pk}/result/"
    )
    assert response.status_code == 200
    assert response.data["published"] is True
    assert response.data["gpa"] == "4.00"


@pytest.mark.integration
def test_a_student_cannot_see_someone_elses_result(
    student_portal_user, as_user, programme, academic_year, curriculum_version, semester
):
    from apps.registry.models import Gender
    from apps.registry.services import create_student

    other_student = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Other",
        last_name="Student",
        gender=Gender.MALE,
        curriculum_version_id=curriculum_version.pk,
        reason="test",
    )
    response = as_user(student_portal_user).get(
        f"/api/v1/examinations/students/{other_student.pk}/semesters/{semester.pk}/result/"
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_missing_marks_report_endpoint(
    examinations_officer, as_user, registration, course, semester
):
    services.create_assessment(course_id=course.pk, name="CA1", weight_percent=Decimal("50"))
    services.create_assessment(course_id=course.pk, name="Final", weight_percent=Decimal("50"))
    response = as_user(examinations_officer).get(
        f"/api/v1/examinations/missing-marks/?course={course.pk}&semester={semester.pk}"
    )
    assert response.status_code == 200
    assert len(response.data) == 2
