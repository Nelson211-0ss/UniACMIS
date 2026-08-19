"""
Examinations service layer (FR-EXM-01…08): weighting, moderation, irregularity
handling, the approve-then-publish gate, and the withheld-on-a-hold result.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.core.providers.holds import set_demo_balance
from apps.enrollment.services import register_course
from apps.examinations import services
from apps.examinations.models import ApprovalStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def registration(student, course, semester, registrar):
    return register_course(
        student_id=student.pk, course_id=course.pk, semester_id=semester.pk, actor=registrar
    )


@pytest.fixture
def full_scheme(course):
    ca1 = services.create_assessment(
        course_id=course.pk, name="CA1", weight_percent=Decimal("20"), max_score=Decimal("20")
    )
    ca2 = services.create_assessment(
        course_id=course.pk, name="CA2", weight_percent=Decimal("20"), max_score=Decimal("20")
    )
    final = services.create_assessment(
        course_id=course.pk, name="Final", weight_percent=Decimal("60"), max_score=Decimal("100")
    )
    return ca1, ca2, final


# ---------------------------------------------------------------- assessments


def test_creating_an_assessment(course):
    assessment = services.create_assessment(
        course_id=course.pk, name="CA1", weight_percent=Decimal("40")
    )
    assert assessment.pk is not None


def test_validating_weights_fails_with_no_assessments(course):
    with pytest.raises(services.ConfigurationError):
        services.validate_assessment_weights(course.pk)


def test_validating_weights_fails_when_they_do_not_sum_to_100(course):
    services.create_assessment(course_id=course.pk, name="CA1", weight_percent=Decimal("40"))
    with pytest.raises(services.ConfigurationError):
        services.validate_assessment_weights(course.pk)


def test_validating_weights_passes_at_exactly_100(course, full_scheme):
    services.validate_assessment_weights(course.pk)


# ----------------------------------------------------------------------- marks


def test_recording_a_mark(registration, full_scheme):
    ca1, _, _ = full_scheme
    mark = services.record_mark(
        registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("18"), actor=None
    )
    assert mark.score == Decimal("18")
    assert mark.is_late is False


def test_a_score_above_the_maximum_is_rejected(registration, full_scheme):
    from django.core.exceptions import ValidationError

    ca1, _, _ = full_scheme
    with pytest.raises(ValidationError):
        services.record_mark(
            registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("25"), actor=None
        )


def test_resubmitting_a_mark_corrects_rather_than_duplicates(registration, full_scheme):
    from apps.examinations.models import Mark

    ca1, _, _ = full_scheme
    services.record_mark(
        registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("10"), actor=None
    )
    services.record_mark(
        registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("15"), actor=None
    )
    assert Mark.objects.filter(registration=registration, assessment=ca1).count() == 1
    assert Mark.objects.get(registration=registration, assessment=ca1).score == Decimal("15")


def test_a_late_mark_is_flagged(registration, course):
    from datetime import timedelta

    from django.utils import timezone

    late_assessment = services.create_assessment(
        course_id=course.pk,
        name="Late CA",
        weight_percent=Decimal("100"),
        grade_entry_deadline=timezone.now() - timedelta(days=1),
    )
    mark = services.record_mark(
        registration_id=registration.pk,
        assessment_id=late_assessment.pk,
        score=Decimal("50"),
        actor=None,
    )
    assert mark.is_late is True


def test_marking_a_dropped_registration_is_rejected(registration, full_scheme, student):
    from apps.enrollment.services import drop_course

    ca1, _, _ = full_scheme
    drop_course(registration, reason="Timetable clash")
    with pytest.raises(services.DroppedRegistration):
        services.record_mark(
            registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("10"), actor=None
        )


def test_moderating_a_mark(registration, full_scheme, hod):
    ca1, _, _ = full_scheme
    mark = services.record_mark(
        registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("10"), actor=None
    )
    moderated = services.moderate_mark(
        mark,
        moderated_score=Decimal("14"),
        notes="Re-checked against the marking scheme",
        actor=hod,
    )
    assert moderated.effective_score == Decimal("14")


def test_moderating_without_a_reason_is_rejected(registration, full_scheme, hod):
    ca1, _, _ = full_scheme
    mark = services.record_mark(
        registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("10"), actor=None
    )
    with pytest.raises(services.ReasonRequired):
        services.moderate_mark(mark, moderated_score=Decimal("14"), notes="  ", actor=hod)


def test_flagging_and_clearing_an_irregularity(registration, full_scheme, examinations_officer):
    ca1, _, _ = full_scheme
    mark = services.record_mark(
        registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("10"), actor=None
    )
    flagged = services.flag_irregularity(
        mark, notes="Suspected impersonation", actor=examinations_officer
    )
    assert flagged.is_irregular is True

    cleared = services.clear_irregularity(
        flagged, actor=examinations_officer, notes="Cleared by panel"
    )
    assert cleared.is_irregular is False


def test_missing_marks_report(registration, full_scheme):
    ca1, _ca2, _final = full_scheme
    services.record_mark(
        registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("18"), actor=None
    )
    report = services.missing_marks_report(registration.course_id, registration.semester_id)
    missing_names = {row["assessment_name"] for row in report}
    assert missing_names == {"CA2", "Final"}


# -------------------------------------------------------------------- results


def test_course_result_is_incomplete_until_every_component_has_a_mark(registration, full_scheme):
    ca1, _, _ = full_scheme
    services.record_mark(
        registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("20"), actor=None
    )
    result = services.course_result(registration.pk)
    assert result["complete"] is False
    assert result["letter"] is None


def test_course_result_computes_a_weighted_percentage_and_grade(
    registration, full_scheme, grading_scale
):
    ca1, ca2, final = full_scheme
    services.record_mark(
        registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("20"), actor=None
    )
    services.record_mark(
        registration_id=registration.pk, assessment_id=ca2.pk, score=Decimal("16"), actor=None
    )
    services.record_mark(
        registration_id=registration.pk, assessment_id=final.pk, score=Decimal("70"), actor=None
    )
    result = services.course_result(registration.pk)
    # 20/20*20 + 16/20*20 + 70/100*60 = 20 + 16 + 42 = 78
    assert result["percent"] == Decimal("78.00")
    assert result["complete"] is True
    assert result["letter"] == "A"
    assert result["is_pass"] is True


def test_a_misconfigured_scheme_blocks_the_grade_not_the_percentage(registration, course):
    services.create_assessment(course_id=course.pk, name="CA1", weight_percent=Decimal("40"))
    services.record_mark(
        registration_id=registration.pk,
        assessment_id=course.assessments.get().pk,
        score=Decimal("40"),
        actor=None,
    )
    result = services.course_result(registration.pk)
    assert result["configuration_error"] is not None
    assert result["complete"] is False
    assert result["letter"] is None


def test_an_irregular_mark_blocks_the_grade(
    registration, full_scheme, examinations_officer, grading_scale
):
    ca1, ca2, final = full_scheme
    services.record_mark(
        registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("20"), actor=None
    )
    services.record_mark(
        registration_id=registration.pk, assessment_id=ca2.pk, score=Decimal("16"), actor=None
    )
    mark = services.record_mark(
        registration_id=registration.pk, assessment_id=final.pk, score=Decimal("70"), actor=None
    )
    services.flag_irregularity(mark, notes="Suspected malpractice", actor=examinations_officer)

    result = services.course_result(registration.pk)
    assert result["has_irregularity"] is True
    assert result["letter"] is None


# ---------------------------------------------------------------- gpa & result


def test_semester_gpa_averages_complete_results_only(
    registration, full_scheme, grading_scale, student, semester
):
    ca1, ca2, final = full_scheme
    services.record_mark(
        registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("20"), actor=None
    )
    services.record_mark(
        registration_id=registration.pk, assessment_id=ca2.pk, score=Decimal("16"), actor=None
    )
    services.record_mark(
        registration_id=registration.pk, assessment_id=final.pk, score=Decimal("70"), actor=None
    )
    gpa = services.semester_gpa(student.pk, semester.pk)
    assert gpa == Decimal("4.00")  # a 78% is an "A" on the fixture scale


def test_student_result_is_unpublished_by_default(student, semester):
    result = services.student_result(student.pk, semester.pk)
    assert result["published"] is False


def test_student_result_after_full_approval_and_publish(
    registration, full_scheme, grading_scale, student, semester, senate_member, examinations_officer
):
    ca1, ca2, final = full_scheme
    services.record_mark(
        registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("20"), actor=None
    )
    services.record_mark(
        registration_id=registration.pk, assessment_id=ca2.pk, score=Decimal("16"), actor=None
    )
    services.record_mark(
        registration_id=registration.pk, assessment_id=final.pk, score=Decimal("70"), actor=None
    )

    approval = services.submit_for_approval(
        semester_id=semester.pk, programme_id=None, actor=examinations_officer
    )
    services.approve_results(approval, actor=senate_member)
    services.publish_results(approval, actor=examinations_officer)

    result = services.student_result(student.pk, semester.pk)
    assert result["published"] is True
    assert result["withheld"] is False
    assert result["gpa"] == Decimal("4.00")


def test_a_result_cannot_be_published_before_approval(semester, examinations_officer):
    approval = services.submit_for_approval(
        semester_id=semester.pk, programme_id=None, actor=examinations_officer
    )
    with pytest.raises(services.InvalidApprovalTransition):
        services.publish_results(approval, actor=examinations_officer)


def test_senate_can_reject_and_the_office_can_resubmit(
    semester, examinations_officer, senate_member
):
    approval = services.submit_for_approval(
        semester_id=semester.pk, programme_id=None, actor=examinations_officer
    )
    rejected = services.reject_results(approval, actor=senate_member, notes="Moderation incomplete")
    assert rejected.status == ApprovalStatus.REJECTED

    resubmitted = services.submit_for_approval(
        semester_id=semester.pk, programme_id=None, actor=examinations_officer
    )
    assert resubmitted.status == ApprovalStatus.PENDING


def test_a_published_result_is_withheld_behind_a_blocking_hold(
    registration, full_scheme, grading_scale, student, semester, senate_member, examinations_officer
):
    ca1, ca2, final = full_scheme
    services.record_mark(
        registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("20"), actor=None
    )
    services.record_mark(
        registration_id=registration.pk, assessment_id=ca2.pk, score=Decimal("16"), actor=None
    )
    services.record_mark(
        registration_id=registration.pk, assessment_id=final.pk, score=Decimal("70"), actor=None
    )
    approval = services.submit_for_approval(
        semester_id=semester.pk, programme_id=None, actor=examinations_officer
    )
    services.approve_results(approval, actor=senate_member)
    services.publish_results(approval, actor=examinations_officer)

    set_demo_balance(student.pk, Decimal("50000"))
    result = services.student_result(student.pk, semester.pk)
    assert result["published"] is True
    assert result["withheld"] is True
    assert result["courses"] == []


# ------------------------------------------------------------------- appeals


def test_submitting_and_upholding_an_appeal(registration, full_scheme, hod):
    ca1, _, _ = full_scheme
    services.record_mark(
        registration_id=registration.pk, assessment_id=ca1.pk, score=Decimal("10"), actor=None
    )
    appeal = services.submit_appeal(
        registration_id=registration.pk,
        assessment_id=ca1.pk,
        reason="I believe question 3 was marked incorrectly",
        actor=None,
    )
    decided = services.decide_appeal(
        appeal, decision="upheld", notes="Re-marked and confirmed an error", actor=hod
    )
    assert decided.status == "upheld"


def test_an_appeal_cannot_be_decided_twice(registration, full_scheme, hod):
    ca1, _, _ = full_scheme
    appeal = services.submit_appeal(
        registration_id=registration.pk,
        assessment_id=ca1.pk,
        reason="Disputing the mark",
        actor=None,
    )
    services.decide_appeal(appeal, decision="rejected", notes="Mark confirmed correct", actor=hod)
    with pytest.raises(services.AppealAlreadyDecided):
        services.decide_appeal(appeal, decision="upheld", notes="Changed my mind", actor=hod)


def test_submitting_an_appeal_without_a_reason_is_rejected(registration, full_scheme):
    ca1, _, _ = full_scheme
    with pytest.raises(services.ReasonRequired):
        services.submit_appeal(
            registration_id=registration.pk, assessment_id=ca1.pk, reason="   ", actor=None
        )
