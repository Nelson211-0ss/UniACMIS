"""
Enrollment API: a student manages their own registrations; a lecturer/HOD see
their department's; only the registrar can override a hold or record a
completion (FR-ENR-01…05).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.core.providers.holds import set_demo_balance
from apps.enrollment import services

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/enrollment/registrations/"


@pytest.fixture
def student_user(roles, user_factory, student):
    """Links the registry `student` fixture to a portal account holding the
    `student` role, so ScopedQuerysetMixin's `student__user` filter matches."""
    user = user_factory(role="student", email="student-portal@test.ss")
    student.user = user
    student.save(update_fields=["user"])
    return user


@pytest.mark.integration
def test_a_student_can_register_for_a_course(student_user, student, course, semester, as_user):
    response = as_user(student_user).post(
        LIST_URL,
        {"student": student.pk, "course": course.pk, "semester": semester.pk},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["status"] == "registered"
    assert response.data["course_code"] == course.code


@pytest.mark.integration
def test_an_invalid_course_id_is_a_clean_validation_error(student_user, student, semester, as_user):
    response = as_user(student_user).post(
        LIST_URL, {"student": student.pk, "course": 999999, "semester": semester.pk}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.integration
def test_a_student_sees_only_their_own_registrations(
    student_user,
    student,
    course,
    semester,
    as_user,
    registrar,
    programme,
    academic_year,
    curriculum_version,
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
    services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=semester.pk, actor=registrar
    )
    services.register_course(
        student_id=other_student.pk, course_id=course.pk, semester_id=semester.pk, actor=registrar
    )

    response = as_user(student_user).get(LIST_URL)
    assert response.status_code == 200
    student_ids = {row["student"] for row in response.data["results"]}
    assert student_ids == {student.pk}


@pytest.mark.integration
def test_the_registrar_sees_every_registration(
    student_user,
    student,
    course,
    semester,
    as_user,
    registrar,
    programme,
    academic_year,
    curriculum_version,
):
    from apps.registry.models import Gender
    from apps.registry.services import create_student

    other_student = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Other2",
        last_name="Student2",
        gender=Gender.FEMALE,
        curriculum_version_id=curriculum_version.pk,
        reason="test",
    )
    services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=semester.pk, actor=registrar
    )
    services.register_course(
        student_id=other_student.pk, course_id=course.pk, semester_id=semester.pk, actor=registrar
    )

    response = as_user(registrar).get(LIST_URL)
    assert response.status_code == 200
    student_ids = {row["student"] for row in response.data["results"]}
    assert {student.pk, other_student.pk} <= student_ids


@pytest.mark.integration
def test_a_lecturer_sees_only_their_departments_registrations(
    roles, staff_factory, student, course, semester, as_user, registrar
):
    lecturer = staff_factory(
        "lecturer", email="lect-enr-api@test.ss"
    )  # same department as `course`
    services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=semester.pk, actor=registrar
    )

    response = as_user(lecturer).get(LIST_URL)
    assert response.status_code == 200
    assert len(response.data["results"]) == 1


@pytest.mark.integration
def test_a_student_can_drop_their_own_course(student_user, student, course, semester, as_user):
    registration = services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=semester.pk, actor=student_user
    )
    response = as_user(student_user).post(
        f"{LIST_URL}{registration.pk}/drop/", {"reason": "Timetable clash"}, format="json"
    )
    assert response.status_code == 200
    assert response.data["status"] == "dropped"


@pytest.mark.integration
def test_a_student_cannot_drop_someone_elses_registration(
    student_user,
    student,
    course,
    semester,
    as_user,
    registrar,
    programme,
    academic_year,
    curriculum_version,
):
    from apps.registry.models import Gender
    from apps.registry.services import create_student

    other_student = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Other3",
        last_name="Student3",
        gender=Gender.MALE,
        curriculum_version_id=curriculum_version.pk,
        reason="test",
    )
    registration = services.register_course(
        student_id=other_student.pk, course_id=course.pk, semester_id=semester.pk, actor=registrar
    )

    response = as_user(student_user).post(
        f"{LIST_URL}{registration.pk}/drop/", {"reason": "Not mine"}, format="json"
    )
    assert response.status_code == 404  # scoped out entirely


@pytest.mark.integration
def test_only_the_registrar_can_record_a_completion(
    student_user, student, course, semester, as_user
):
    registration = services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=semester.pk, actor=student_user
    )
    denied = as_user(student_user).post(
        f"{LIST_URL}{registration.pk}/complete/",
        {"reason": "Trying to self-certify"},
        format="json",
    )
    assert denied.status_code == 403


@pytest.mark.integration
def test_the_registrar_can_record_a_completion(
    student_user, student, course, semester, as_user, registrar
):
    registration = services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=semester.pk, actor=student_user
    )
    response = as_user(registrar).post(
        f"{LIST_URL}{registration.pk}/complete/",
        {"reason": "Transfer credit from previous institution"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["status"] == "completed"


@pytest.mark.integration
def test_a_student_registering_despite_a_hold_is_blocked(
    student_user, student, course, semester, as_user
):
    set_demo_balance(student.pk, Decimal("50000"))
    response = as_user(student_user).post(
        LIST_URL,
        {"student": student.pk, "course": course.pk, "semester": semester.pk},
        format="json",
    )
    assert response.status_code == 409
    assert response.data["error"]["code"] == "blocked_by_hold"


@pytest.mark.integration
def test_a_student_cannot_override_their_own_hold(student_user, student, course, semester, as_user):
    set_demo_balance(student.pk, Decimal("50000"))
    response = as_user(student_user).post(
        LIST_URL,
        {
            "student": student.pk,
            "course": course.pk,
            "semester": semester.pk,
            "override_reason": "Please let me in",
        },
        format="json",
    )
    assert response.status_code == 409  # lacks enrollment.override_hold


@pytest.mark.integration
def test_a_registrar_can_override_a_hold_via_the_api(
    student_user, student, course, semester, as_user, registrar
):
    set_demo_balance(student.pk, Decimal("50000"))
    response = as_user(registrar).post(
        LIST_URL,
        {
            "student": student.pk,
            "course": course.pk,
            "semester": semester.pk,
            "override_reason": "Payment plan approved by finance office",
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["status"] == "registered"


@pytest.mark.integration
def test_the_class_list_endpoint(student_user, student, course, semester, as_user, registrar):
    services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=semester.pk, actor=registrar
    )
    response = as_user(registrar).get(
        f"/api/v1/enrollment/class-list/?course={course.pk}&semester={semester.pk}"
    )
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["student_id"] == student.student_id


@pytest.mark.integration
def test_the_class_list_requires_permission(roles, user_factory, course, semester, as_user):
    outsider = user_factory(email="outsider@test.ss")
    response = as_user(outsider).get(
        f"/api/v1/enrollment/class-list/?course={course.pk}&semester={semester.pk}"
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_a_student_can_see_their_own_credit_summary(
    student_user, student, course, semester, as_user
):
    services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=semester.pk, actor=student_user
    )
    response = as_user(student_user).get(
        f"/api/v1/enrollment/credit-summary/{student.pk}/?semester={semester.pk}"
    )
    assert response.status_code == 200
    assert response.data["registered_credits"] == course.credit_hours


@pytest.mark.integration
def test_a_student_cannot_see_someone_elses_credit_summary(
    student_user,
    student,
    course,
    semester,
    as_user,
    registrar,
    programme,
    academic_year,
    curriculum_version,
):
    from apps.registry.models import Gender
    from apps.registry.services import create_student

    other_student = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Other4",
        last_name="Student4",
        gender=Gender.FEMALE,
        curriculum_version_id=curriculum_version.pk,
        reason="test",
    )
    response = as_user(student_user).get(
        f"/api/v1/enrollment/credit-summary/{other_student.pk}/?semester={semester.pk}"
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_the_registrar_can_see_any_students_credit_summary(
    student, course, semester, as_user, registrar
):
    services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=semester.pk, actor=registrar
    )
    response = as_user(registrar).get(
        f"/api/v1/enrollment/credit-summary/{student.pk}/?semester={semester.pk}"
    )
    assert response.status_code == 200
    assert response.data["registered_credits"] == course.credit_hours
