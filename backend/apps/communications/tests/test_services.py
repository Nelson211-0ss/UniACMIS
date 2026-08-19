"""Communications service layer (FR-COM-01…03)."""

from __future__ import annotations

import pytest

from apps.communications import services
from apps.communications.models import AudienceType
from apps.core.providers import get_notification_provider, reset_provider_cache
from apps.registry.models import Gender
from apps.registry.services import create_student

pytestmark = pytest.mark.django_db


@pytest.fixture
def recording_notifications(settings):
    settings.NOTIFICATION_PROVIDER = (
        "apps.core.providers.notifications.RecordingNotificationProvider"
    )
    reset_provider_cache()
    yield
    reset_provider_cache()


@pytest.fixture
def reachable_student(programme, curriculum_version, academic_year):
    return create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Nyandeng",
        last_name="Malek",
        gender=Gender.FEMALE,
        curriculum_version_id=curriculum_version.pk,
        phone="+211920000010",
        email="nyandeng@example.ss",
        reason="test",
    )


def test_broadcasting_to_all_students_requires_the_permission(reachable_student, hod):
    with pytest.raises(services.BroadcastNotPermitted):
        services.send_announcement(
            title="Semester begins",
            body="Classes resume Monday.",
            audience_type=AudienceType.ALL_STUDENTS,
            actor=hod,
        )


def test_registrar_can_broadcast_to_all_students(
    recording_notifications, reachable_student, registrar
):
    announcement = services.send_announcement(
        title="Semester begins",
        body="Classes resume Monday.",
        audience_type=AudienceType.ALL_STUDENTS,
        actor=registrar,
    )
    assert announcement.recipient_count == 1
    assert announcement.sms_sent_count == 1
    assert announcement.email_sent_count == 1

    provider = get_notification_provider()
    assert len(provider.sent) == 2


def test_a_class_announcement_requires_a_programme(registrar):
    with pytest.raises(services.ProgrammeRequired):
        services.send_announcement(
            title="Venue change",
            body="Room 4B instead.",
            audience_type=AudienceType.PROGRAMME,
            actor=registrar,
        )


def test_a_hod_can_announce_to_their_own_department(
    recording_notifications, reachable_student, hod, programme
):
    announcement = services.send_announcement(
        title="Venue change",
        body="Room 4B instead.",
        audience_type=AudienceType.PROGRAMME,
        programme_id=programme.pk,
        actor=hod,
    )
    assert announcement.recipient_count == 1


def test_a_hod_cannot_announce_to_another_departments_programme(hod, department, faculty):
    from apps.curriculum.models import Award, Programme

    other_department = department.__class__.objects.create(
        faculty=faculty, code="MEC", name="Mechanical Engineering"
    )
    other_programme = Programme.objects.create(
        department=other_department,
        code="MEC-BSC",
        name="BSc Mechanical Engineering",
        award=Award.BACHELOR,
        duration_years=5,
        total_credits_required=180,
        min_credits_per_semester=12,
        max_credits_per_semester=24,
    )
    with pytest.raises(services.OutsideOwnDepartment):
        services.send_announcement(
            title="Venue change",
            body="Room 4B instead.",
            audience_type=AudienceType.PROGRAMME,
            programme_id=other_programme.pk,
            actor=hod,
        )


def test_a_recipient_with_no_contact_details_is_simply_not_counted(
    recording_notifications, programme, curriculum_version, academic_year, registrar
):
    create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Unreachable",
        last_name="Student",
        gender=Gender.MALE,
        curriculum_version_id=curriculum_version.pk,
        reason="test",
    )
    announcement = services.send_announcement(
        title="Semester begins",
        body="Classes resume Monday.",
        audience_type=AudienceType.ALL_STUDENTS,
        actor=registrar,
    )
    assert announcement.recipient_count == 1
    assert announcement.sms_sent_count == 0
    assert announcement.email_sent_count == 0


def test_messaging_alumni_requires_broadcast_all(student, hod):
    from apps.alumni import services as alumni_services
    from apps.registry.services import change_status

    change_status(student, new_status="graduated", reason="Completed programme")
    alumni_services.create_alumni_profile(student_id=student.pk, phone="+211920000099")

    with pytest.raises(services.BroadcastNotPermitted):
        services.send_announcement(
            title="Reunion",
            body="Join us in December.",
            audience_type=AudienceType.ALUMNI,
            actor=hod,
        )


def test_registrar_can_message_alumni(recording_notifications, student, registrar):
    from apps.alumni import services as alumni_services
    from apps.registry.services import change_status

    change_status(student, new_status="graduated", reason="Completed programme")
    alumni_services.create_alumni_profile(
        student_id=student.pk, phone="+211920000099", email="alum@example.ss"
    )

    announcement = services.send_announcement(
        title="Reunion",
        body="Join us in December.",
        audience_type=AudienceType.ALUMNI,
        actor=registrar,
    )
    assert announcement.recipient_count == 1
    assert announcement.sms_sent_count == 1
    assert announcement.email_sent_count == 1
