"""Alumni service layer (FR-ALM-01…02)."""

from __future__ import annotations

from datetime import date

import pytest

from apps.alumni import services
from apps.alumni.models import EmploymentStatus
from apps.registry.services import change_status

pytestmark = pytest.mark.django_db


def test_creating_a_profile_for_a_graduate(student):
    change_status(student, new_status="graduated", reason="Completed programme")
    profile = services.create_alumni_profile(
        student_id=student.pk, phone="+211920000099", employment_status=EmploymentStatus.EMPLOYED
    )
    assert profile.pk is not None
    assert profile.employment_status == EmploymentStatus.EMPLOYED


def test_a_profile_cannot_be_created_before_graduation(student):
    with pytest.raises(services.NotYetGraduated):
        services.create_alumni_profile(student_id=student.pk)


def test_updating_a_profile(student):
    change_status(student, new_status="graduated", reason="Completed programme")
    profile = services.create_alumni_profile(student_id=student.pk)
    updated = services.update_alumni_profile(profile, current_employer="Ministry of Health")
    assert updated.current_employer == "Ministry of Health"


def test_scheduling_an_alumni_event():
    event = services.create_alumni_event(
        title="Class of 2020 reunion", event_date=date(2026, 12, 1), location="Main campus"
    )
    assert event.pk is not None


def test_active_alumni_contacts_excludes_the_uncontactable(
    student, programme, curriculum_version, academic_year
):
    from apps.registry.models import Gender
    from apps.registry.services import create_student

    change_status(student, new_status="graduated", reason="Completed programme")
    services.create_alumni_profile(student_id=student.pk, phone="+211920000099")

    opted_out_student = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Opted",
        last_name="Out",
        gender=Gender.MALE,
        curriculum_version_id=curriculum_version.pk,
        reason="test",
    )
    change_status(opted_out_student, new_status="graduated", reason="Completed programme")
    services.create_alumni_profile(
        student_id=opted_out_student.pk, phone="+211920000098", is_contactable=False
    )

    contacts = services.active_alumni_contacts()
    assert len(contacts) == 1
    assert contacts[0]["phone"] == "+211920000099"
