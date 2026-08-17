"""
Student status transitions (FR-REG-04).

Status is not a free-text field a clerk can set to anything: the allowed moves are
declared, a reason is always required, and every change opens a history entry.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.registry.models import StudentStatus, StudentStatusHistory
from apps.registry.services import InvalidStatusTransition, change_status

pytestmark = pytest.mark.django_db


def test_a_new_student_starts_active_with_an_opening_history_entry(student):
    assert student.status == StudentStatus.ACTIVE

    history = StudentStatusHistory.objects.filter(student=student)
    assert history.count() == 1
    entry = history.first()
    assert entry.from_status == ""
    assert entry.to_status == StudentStatus.ACTIVE


def test_a_permitted_transition_is_recorded(student, registrar):
    change_status(
        student,
        StudentStatus.SUSPENDED,
        reason="Disciplinary case opened",
        actor=registrar,
        reference="SEN/14/2026",
    )

    student.refresh_from_db()
    assert student.status == StudentStatus.SUSPENDED

    entry = StudentStatusHistory.objects.filter(student=student).first()
    assert entry.from_status == StudentStatus.ACTIVE
    assert entry.to_status == StudentStatus.SUSPENDED
    assert entry.reason == "Disciplinary case opened"
    assert entry.reference == "SEN/14/2026"
    assert entry.changed_by == registrar


def test_a_reason_is_required(student):
    with pytest.raises(InvalidStatusTransition, match="reason is required"):
        change_status(student, StudentStatus.WITHDRAWN, reason="")


def test_a_whitespace_reason_is_not_a_reason(student):
    with pytest.raises(InvalidStatusTransition, match="reason is required"):
        change_status(student, StudentStatus.WITHDRAWN, reason="   ")


def test_an_unreachable_transition_is_refused(student):
    change_status(student, StudentStatus.DEFERRED, reason="Deferred for a year")
    # Deferred → suspended makes no sense: they are not currently studying.
    with pytest.raises(InvalidStatusTransition, match="cannot go from"):
        change_status(student, StudentStatus.SUSPENDED, reason="Attempted")


def test_graduated_is_terminal(student):
    change_status(student, StudentStatus.GRADUATED, reason="Completed the programme")
    with pytest.raises(InvalidStatusTransition, match="final status"):
        change_status(student, StudentStatus.ACTIVE, reason="Trying to re-open")


def test_expelled_is_terminal(student):
    change_status(student, StudentStatus.EXPELLED, reason="Examination malpractice")
    with pytest.raises(InvalidStatusTransition, match="final status"):
        change_status(student, StudentStatus.ACTIVE, reason="Trying to reverse")


def test_graduating_sets_the_graduation_date(student):
    change_status(student, StudentStatus.GRADUATED, reason="Completed the programme")
    student.refresh_from_db()
    assert student.graduated_on is not None


def test_an_explicit_effective_date_is_kept(student):
    backdated = timezone.localdate() - timedelta(days=30)
    change_status(
        student,
        StudentStatus.WITHDRAWN,
        reason="Withdrew last month; paperwork arrived late",
        effective_date=backdated,
    )
    # Fetched by the transition, not by ordering: history sorts newest-first by
    # effective date, so a backdated entry is deliberately not the first row.
    entry = StudentStatusHistory.objects.get(student=student, to_status=StudentStatus.WITHDRAWN)
    assert entry.effective_date == backdated


def test_setting_the_same_status_is_a_no_op(student):
    before = StudentStatusHistory.objects.filter(student=student).count()
    change_status(student, StudentStatus.ACTIVE, reason="No change")
    assert StudentStatusHistory.objects.filter(student=student).count() == before


def test_a_suspended_student_can_return(student):
    change_status(student, StudentStatus.SUSPENDED, reason="Suspended")
    change_status(student, StudentStatus.ACTIVE, reason="Case dismissed; reinstated")
    student.refresh_from_db()
    assert student.status == StudentStatus.ACTIVE
    assert StudentStatusHistory.objects.filter(student=student).count() == 3


def test_history_is_ordered_newest_first(student):
    change_status(student, StudentStatus.SUSPENDED, reason="One")
    change_status(student, StudentStatus.ACTIVE, reason="Two")

    statuses = list(
        StudentStatusHistory.objects.filter(student=student).values_list("to_status", flat=True)
    )
    assert statuses[0] == StudentStatus.ACTIVE
