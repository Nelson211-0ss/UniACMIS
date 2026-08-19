"""Communications API: sending is gated (institution-wide only for those
who hold `broadcast_all`); reading an announcement is open to whoever is in
its audience (FR-COM-01…03)."""

from __future__ import annotations

import pytest

from apps.communications import services
from apps.communications.models import AudienceType

pytestmark = pytest.mark.django_db

ANNOUNCEMENTS_URL = "/api/v1/communications/announcements/"


@pytest.fixture
def recording_notifications(settings):
    from apps.core.providers import reset_provider_cache

    settings.NOTIFICATION_PROVIDER = (
        "apps.core.providers.notifications.RecordingNotificationProvider"
    )
    reset_provider_cache()
    yield
    reset_provider_cache()


@pytest.mark.integration
def test_registrar_can_broadcast(recording_notifications, registrar, as_user):
    response = as_user(registrar).post(
        f"{ANNOUNCEMENTS_URL}send/",
        {
            "title": "Semester begins",
            "body": "Classes resume Monday.",
            "audience_type": "all_students",
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["audience_type"] == "all_students"


@pytest.mark.integration
def test_a_hod_cannot_broadcast_institution_wide(hod, as_user):
    response = as_user(hod).post(
        f"{ANNOUNCEMENTS_URL}send/",
        {
            "title": "Semester begins",
            "body": "Classes resume Monday.",
            "audience_type": "all_students",
        },
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.integration
def test_a_lecturer_cannot_send_any_announcement(lecturer, as_user):
    response = as_user(lecturer).post(
        f"{ANNOUNCEMENTS_URL}send/",
        {
            "title": "Semester begins",
            "body": "Classes resume Monday.",
            "audience_type": "all_students",
        },
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_a_hod_can_announce_to_their_own_class(recording_notifications, hod, as_user, programme):
    response = as_user(hod).post(
        f"{ANNOUNCEMENTS_URL}send/",
        {
            "title": "Venue change",
            "body": "Room 4B instead.",
            "audience_type": "programme",
            "programme": programme.pk,
        },
        format="json",
    )
    assert response.status_code == 201


@pytest.mark.integration
def test_a_student_sees_all_students_and_their_own_class_announcements(
    student_portal_user, as_user, registrar, programme
):
    services.send_announcement(
        title="Semester begins",
        body="...",
        audience_type=AudienceType.ALL_STUDENTS,
        actor=registrar,
    )
    services.send_announcement(
        title="Own class notice",
        body="...",
        audience_type=AudienceType.PROGRAMME,
        programme_id=programme.pk,
        actor=registrar,
    )

    response = as_user(student_portal_user).get(ANNOUNCEMENTS_URL)
    assert response.status_code == 200
    titles = {row["title"] for row in response.data["results"]}
    assert titles == {"Semester begins", "Own class notice"}


@pytest.mark.integration
def test_a_student_does_not_see_another_programmes_announcement(
    student_portal_user, as_user, registrar, department, faculty
):
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
    services.send_announcement(
        title="Not for you",
        body="...",
        audience_type=AudienceType.PROGRAMME,
        programme_id=other_programme.pk,
        actor=registrar,
    )

    response = as_user(student_portal_user).get(ANNOUNCEMENTS_URL)
    assert response.status_code == 200
    titles = {row["title"] for row in response.data["results"]}
    assert "Not for you" not in titles
