"""Alumni API: registrar-managed, no self-service portal (FR-ALM-01…02)."""

from __future__ import annotations

import pytest

from apps.registry.services import change_status

pytestmark = pytest.mark.django_db

PROFILES_URL = "/api/v1/alumni/profiles/"
EVENTS_URL = "/api/v1/alumni/events/"


@pytest.mark.integration
def test_registrar_can_create_an_alumni_profile(registrar, as_user, student):
    change_status(student, new_status="graduated", reason="Completed programme")
    response = as_user(registrar).post(PROFILES_URL, {"student": student.pk}, format="json")
    assert response.status_code == 201


@pytest.mark.integration
def test_a_lecturer_cannot_create_an_alumni_profile(lecturer, as_user, student):
    change_status(student, new_status="graduated", reason="Completed programme")
    response = as_user(lecturer).post(PROFILES_URL, {"student": student.pk}, format="json")
    assert response.status_code == 403


@pytest.mark.integration
def test_a_profile_for_an_active_student_is_rejected(registrar, as_user, student):
    response = as_user(registrar).post(PROFILES_URL, {"student": student.pk}, format="json")
    assert response.status_code == 400


@pytest.mark.integration
def test_registrar_can_schedule_an_alumni_event(registrar, as_user):
    response = as_user(registrar).post(
        EVENTS_URL,
        {"title": "Class of 2020 reunion", "event_date": "2026-12-01", "location": "Main campus"},
        format="json",
    )
    assert response.status_code == 201


@pytest.mark.integration
def test_a_student_cannot_view_alumni_events(student_portal_user, as_user):
    response = as_user(student_portal_user).get(EVENTS_URL)
    assert response.status_code == 403
