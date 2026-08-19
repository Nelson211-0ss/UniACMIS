"""
Enrollment service layer (FR-ENR-01…05).

The point of this module is that nothing here reimplements a rule Phase 1
already built: the calendar window, the prerequisite/credit checks and the
hold registry are called, not reproduced. These tests exercise the composition,
not the underlying mechanisms — those already have their own test suites.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.exceptions import BlockedByHold
from apps.core.providers.holds import set_demo_balance
from apps.curriculum.models import Prerequisite
from apps.enrollment import services
from apps.enrollment.models import CourseRegistration, RegistrationStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def open_semester(semester):
    """The shared `semester` fixture already has registration open; alias for
    readability in this module."""
    return semester


@pytest.fixture
def closed_semester(academic_year):
    from apps.academics.models import Semester

    today = timezone.localdate()
    return Semester.objects.create(
        academic_year=academic_year,
        sequence=2,
        name="Semester 2",
        teaching_start=today + timedelta(days=120),
        teaching_end=today + timedelta(days=220),
        registration_opens=timezone.now() - timedelta(days=30),
        registration_closes=timezone.now() - timedelta(days=20),  # closed
        add_drop_closes=timezone.now() - timedelta(days=10),
    )


@pytest.fixture
def second_course(department):
    from apps.curriculum.models import Course

    return Course.objects.create(
        department=department, code="CVE201", title="Strength of Materials", credit_hours=4, level=2
    )


# --------------------------------------------------------------- registration


@pytest.mark.integration
def test_registering_creates_a_registration(student, course, open_semester, registrar):
    registration = services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=open_semester.pk, actor=registrar
    )
    assert registration.status == RegistrationStatus.REGISTERED
    assert registration.is_repeat is False
    assert registration.registered_by == registrar


@pytest.mark.integration
def test_registration_uses_the_current_semester_by_default(
    student, course, open_semester, registrar
):
    registration = services.register_course(
        student_id=student.pk, course_id=course.pk, actor=registrar
    )
    assert registration.semester_id == open_semester.pk


@pytest.mark.integration
def test_registration_is_refused_when_the_window_is_closed(
    student, course, closed_semester, registrar
):
    from apps.academics.services.calendar import WindowClosed

    with pytest.raises(WindowClosed):
        services.register_course(
            student_id=student.pk,
            course_id=course.pk,
            semester_id=closed_semester.pk,
            actor=registrar,
        )


@pytest.mark.integration
def test_registering_twice_is_refused(student, course, open_semester, registrar):
    services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=open_semester.pk, actor=registrar
    )
    with pytest.raises(services.AlreadyRegistered):
        services.register_course(
            student_id=student.pk,
            course_id=course.pk,
            semester_id=open_semester.pk,
            actor=registrar,
        )


# -------------------------------------------------------------- prerequisites


@pytest.mark.integration
def test_an_unmet_prerequisite_blocks_registration(
    student, course, second_course, open_semester, registrar
):
    Prerequisite.objects.create(course=second_course, required_course=course)

    with pytest.raises(services.PrerequisiteNotMet) as raised:
        services.register_course(
            student_id=student.pk,
            course_id=second_course.pk,
            semester_id=open_semester.pk,
            actor=registrar,
        )
    assert raised.value.details["unmet"][0]["requires"] == course.code


@pytest.mark.integration
def test_completing_the_prerequisite_unblocks_registration(
    student, course, second_course, open_semester, registrar
):
    Prerequisite.objects.create(course=second_course, required_course=course)

    prior = services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=open_semester.pk, actor=registrar
    )
    services.record_prior_completion(prior, actor=registrar, reason="Transfer credit recognised")

    registration = services.register_course(
        student_id=student.pk,
        course_id=second_course.pk,
        semester_id=open_semester.pk,
        actor=registrar,
    )
    assert registration.status == RegistrationStatus.REGISTERED


@pytest.mark.integration
def test_a_course_with_no_prerequisites_registers_freely(student, course, open_semester, registrar):
    registration = services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=open_semester.pk, actor=registrar
    )
    assert registration.status == RegistrationStatus.REGISTERED


# ----------------------------------------------------------------- credit cap


@pytest.mark.integration
def test_exceeding_the_credit_limit_is_refused(
    student, department, open_semester, registrar, programme
):
    from apps.curriculum.models import Course

    programme.max_credits_per_semester = 5
    programme.save()
    heavy_course = Course.objects.create(
        department=department, code="HEAVY1", title="Heavy Course", credit_hours=6, level=1
    )

    with pytest.raises(services.CreditLimitExceeded):
        services.register_course(
            student_id=student.pk,
            course_id=heavy_course.pk,
            semester_id=open_semester.pk,
            actor=registrar,
        )


@pytest.mark.integration
def test_credit_limit_accounts_for_existing_registrations(
    student, department, open_semester, registrar, programme
):
    from apps.curriculum.models import Course

    programme.max_credits_per_semester = 6
    programme.save()
    first = Course.objects.create(
        department=department, code="C1", title="C1", credit_hours=4, level=1
    )
    second = Course.objects.create(
        department=department, code="C2", title="C2", credit_hours=4, level=1
    )

    services.register_course(
        student_id=student.pk, course_id=first.pk, semester_id=open_semester.pk, actor=registrar
    )
    with pytest.raises(services.CreditLimitExceeded) as raised:
        services.register_course(
            student_id=student.pk,
            course_id=second.pk,
            semester_id=open_semester.pk,
            actor=registrar,
        )
    assert raised.value.details["would_be"] == 8


@pytest.mark.integration
def test_a_dropped_courses_credits_do_not_count_against_the_limit(
    student, department, open_semester, registrar, programme
):
    from apps.curriculum.models import Course

    programme.max_credits_per_semester = 4
    programme.save()
    first = Course.objects.create(
        department=department, code="D1", title="D1", credit_hours=4, level=1
    )
    second = Course.objects.create(
        department=department, code="D2", title="D2", credit_hours=4, level=1
    )

    registration = services.register_course(
        student_id=student.pk, course_id=first.pk, semester_id=open_semester.pk, actor=registrar
    )
    services.drop_course(registration, reason="Timetable clash", actor=registrar)

    # Must not raise: the dropped course's credits were released.
    services.register_course(
        student_id=student.pk, course_id=second.pk, semester_id=open_semester.pk, actor=registrar
    )


# ---------------------------------------------------------------------- holds


@pytest.mark.integration
def test_a_blocking_hold_prevents_registration(student, course, open_semester, registrar):
    set_demo_balance(student.pk, Decimal("50000"))
    with pytest.raises(BlockedByHold):
        services.register_course(
            student_id=student.pk,
            course_id=course.pk,
            semester_id=open_semester.pk,
            actor=registrar,
        )


@pytest.mark.integration
def test_a_registrar_can_override_a_hold_with_a_reason(student, course, open_semester, registrar):
    set_demo_balance(student.pk, Decimal("50000"))
    registration = services.register_course(
        student_id=student.pk,
        course_id=course.pk,
        semester_id=open_semester.pk,
        actor=registrar,
        override_reason="Fee waiver approved by the Dean pending processing.",
    )
    assert registration.status == RegistrationStatus.REGISTERED
    assert registration.hold_override_by == registrar
    assert "Dean" in registration.override_reason


@pytest.mark.integration
def test_a_registrar_who_does_not_supply_a_reason_is_blocked_like_anyone_else(
    student, course, open_semester, registrar
):
    """No override_reason means no override was attempted at all — holding the
    permission does not change the outcome of a plain registration attempt."""
    set_demo_balance(student.pk, Decimal("50000"))
    with pytest.raises(BlockedByHold):
        services.register_course(
            student_id=student.pk,
            course_id=course.pk,
            semester_id=open_semester.pk,
            actor=registrar,
        )


@pytest.mark.integration
def test_a_user_without_override_permission_cannot_bypass_a_hold(
    student, course, open_semester, roles, staff_factory
):
    lecturer = staff_factory("lecturer", email="lect-enr@test.ss")
    set_demo_balance(student.pk, Decimal("50000"))
    with pytest.raises(BlockedByHold):
        services.register_course(
            student_id=student.pk,
            course_id=course.pk,
            semester_id=open_semester.pk,
            actor=lecturer,
            override_reason="Trying anyway",
        )


# --------------------------------------------------------------------- repeat


@pytest.mark.integration
def test_re_registering_in_a_later_semester_is_flagged_as_a_repeat(
    student, course, open_semester, registrar, academic_year
):
    from apps.academics.models import Semester

    first_attempt = services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=open_semester.pk, actor=registrar
    )
    services.drop_course(first_attempt, reason="Withdrew", actor=registrar)

    later = Semester.objects.create(
        academic_year=academic_year,
        sequence=3,
        name="Semester 3",
        teaching_start=timezone.localdate() + timedelta(days=200),
        teaching_end=timezone.localdate() + timedelta(days=300),
        registration_opens=timezone.now() - timedelta(days=1),
        registration_closes=timezone.now() + timedelta(days=10),
    )

    retake = services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=later.pk, actor=registrar
    )
    assert retake.is_repeat is True


@pytest.mark.integration
def test_reactivating_a_dropped_registration_in_the_same_semester_is_not_a_repeat(
    student, course, open_semester, registrar
):
    registration = services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=open_semester.pk, actor=registrar
    )
    services.drop_course(registration, reason="Changed my mind", actor=registrar)

    reactivated = services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=open_semester.pk, actor=registrar
    )
    assert reactivated.pk == registration.pk
    assert reactivated.status == RegistrationStatus.REGISTERED
    assert reactivated.is_repeat is False


# ------------------------------------------------------------------------ drop


@pytest.mark.integration
def test_dropping_requires_a_reason(student, course, open_semester, registrar):
    registration = services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=open_semester.pk, actor=registrar
    )
    with pytest.raises(Exception, match="reason is required"):
        services.drop_course(registration, reason="", actor=registrar)


@pytest.mark.integration
def test_only_a_registered_course_can_be_dropped(student, course, open_semester, registrar):
    registration = services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=open_semester.pk, actor=registrar
    )
    services.drop_course(registration, reason="First drop", actor=registrar)
    with pytest.raises(services.RegistrationNotOpen):
        services.drop_course(registration, reason="Second drop", actor=registrar)


@pytest.mark.integration
def test_dropping_after_the_add_drop_window_closes_is_refused(
    student, course, closed_semester, registrar
):
    registration = CourseRegistration.objects.create(
        student=student, course=course, semester=closed_semester, registered_by=registrar
    )
    with pytest.raises(services.RegistrationNotOpen, match="add/drop window"):
        services.drop_course(registration, reason="Too late", actor=registrar)


# ------------------------------------------------------------------ completion


@pytest.mark.integration
def test_completion_requires_a_reason(student, course, open_semester, registrar):
    registration = services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=open_semester.pk, actor=registrar
    )
    with pytest.raises(Exception, match="reason is required"):
        services.record_prior_completion(registration, actor=registrar, reason="")


@pytest.mark.integration
def test_completing_an_already_completed_registration_is_a_no_op(
    student, course, open_semester, registrar
):
    registration = services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=open_semester.pk, actor=registrar
    )
    first = services.record_prior_completion(
        registration, actor=registrar, reason="Transfer credit"
    )
    second = services.record_prior_completion(
        registration, actor=registrar, reason="Transfer credit"
    )
    assert first.completed_at == second.completed_at


# --------------------------------------------------------------- class lists


@pytest.mark.integration
def test_class_list_includes_only_registered_students(
    student, course, open_semester, registrar, department, academic_year, curriculum_version
):
    from apps.registry.models import Gender
    from apps.registry.services import create_student

    other = create_student(
        programme_id=student.programme_id,
        entry_academic_year_id=academic_year.pk,
        first_name="Bbb",
        last_name="Zzz",
        gender=Gender.MALE,
        curriculum_version_id=curriculum_version.pk,
        reason="test",
    )
    reg1 = services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=open_semester.pk, actor=registrar
    )
    services.register_course(
        student_id=other.pk, course_id=course.pk, semester_id=open_semester.pk, actor=registrar
    )
    services.drop_course(reg1, reason="Dropped before the list was pulled", actor=registrar)

    entries = services.class_list(course.pk, open_semester.pk)

    assert len(entries) == 1
    assert entries[0]["student_id"] == other.student_id


@pytest.mark.integration
def test_class_list_is_empty_for_no_registrations(course, open_semester):
    assert services.class_list(course.pk, open_semester.pk) == []


# ------------------------------------------------------------------ summaries


@pytest.mark.integration
def test_credit_summary_reports_load_against_the_programmes_limits(
    student, course, open_semester, registrar, programme
):
    services.register_course(
        student_id=student.pk, course_id=course.pk, semester_id=open_semester.pk, actor=registrar
    )
    summary = services.credit_summary(student.pk, open_semester.pk)
    assert summary["registered_credits"] == course.credit_hours
    assert summary["max_credits"] == programme.max_credits_per_semester
    assert summary["min_credits"] == programme.min_credits_per_semester
