"""Documents API: a student manages their own transcript requests; the
registrar decides them and issues certificates; verification is public
(FR-DOC-01…04)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.core.providers.holds import set_demo_balance
from apps.documents import services

pytestmark = pytest.mark.django_db

TRANSCRIPT_REQUESTS_URL = "/api/v1/documents/transcript-requests/"
ISSUED_URL = "/api/v1/documents/issued/"


@pytest.mark.integration
def test_a_student_can_request_their_own_transcript(student_portal_user, as_user):
    response = as_user(student_portal_user).post(
        f"{TRANSCRIPT_REQUESTS_URL}submit/", {"reason": "Job application"}, format="json"
    )
    assert response.status_code == 201
    assert response.data["status"] == "requested"


@pytest.mark.integration
def test_a_lecturer_cannot_request_a_transcript_for_themselves(lecturer, as_user):
    response = as_user(lecturer).post(f"{TRANSCRIPT_REQUESTS_URL}submit/", {}, format="json")
    assert response.status_code == 403


@pytest.mark.integration
def test_registrar_can_file_a_request_on_a_students_behalf(registrar, as_user, student):
    response = as_user(registrar).post(
        f"{TRANSCRIPT_REQUESTS_URL}submit/",
        {"student": student.pk, "reason": "Walk-in, no portal account"},
        format="json",
    )
    assert response.status_code == 201


@pytest.mark.integration
def test_a_lecturer_cannot_file_a_request_on_a_students_behalf(lecturer, as_user, student):
    response = as_user(lecturer).post(
        f"{TRANSCRIPT_REQUESTS_URL}submit/", {"student": student.pk}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_a_student_only_sees_their_own_requests(
    student_portal_user, as_user, programme, curriculum_version, academic_year
):
    from apps.registry.models import Gender
    from apps.registry.services import create_student

    other_student = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Other",
        last_name="Requester",
        gender=Gender.FEMALE,
        curriculum_version_id=curriculum_version.pk,
        reason="test",
    )
    as_user(student_portal_user).post(f"{TRANSCRIPT_REQUESTS_URL}submit/", {}, format="json")
    services.request_transcript(student_id=other_student.pk)

    response = as_user(student_portal_user).get(TRANSCRIPT_REQUESTS_URL)
    assert response.status_code == 200
    assert {row["student"] for row in response.data["results"]} == {
        student_portal_user.student_profile.pk
    }


@pytest.mark.integration
def test_registrar_decides_a_transcript_request(registrar, as_user, student):
    request = services.request_transcript(student_id=student.pk)
    response = as_user(registrar).post(
        f"{TRANSCRIPT_REQUESTS_URL}{request.pk}/decide/",
        {"approve": True, "notes": "Verified"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["status"] == "issued"


@pytest.mark.integration
def test_a_lecturer_cannot_decide_a_transcript_request(lecturer, as_user, student):
    request = services.request_transcript(student_id=student.pk)
    response = as_user(lecturer).post(
        f"{TRANSCRIPT_REQUESTS_URL}{request.pk}/decide/",
        {"approve": True, "notes": "Verified"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_registrar_can_issue_a_certificate(registrar, as_user, student):
    response = as_user(registrar).post(
        f"{ISSUED_URL}issue-certificate/", {"student": student.pk}, format="json"
    )
    assert response.status_code == 201
    assert response.data["document_type"] == "certificate"


@pytest.mark.integration
def test_issuing_a_certificate_is_blocked_by_a_hold(registrar, as_user, student):
    set_demo_balance(student.pk, Decimal("50000"))
    response = as_user(registrar).post(
        f"{ISSUED_URL}issue-certificate/", {"student": student.pk}, format="json"
    )
    assert response.status_code == 409


@pytest.mark.integration
def test_a_student_only_sees_their_own_issued_documents(
    student_portal_user, as_user, registrar, programme, curriculum_version, academic_year
):
    from apps.registry.models import Gender
    from apps.registry.services import create_student

    other_student = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Other",
        last_name="Graduate",
        gender=Gender.FEMALE,
        curriculum_version_id=curriculum_version.pk,
        reason="test",
    )
    services.issue_certificate(student_id=other_student.pk, actor=registrar)
    services.issue_certificate(student_id=student_portal_user.student_profile.pk, actor=registrar)

    response = as_user(student_portal_user).get(ISSUED_URL)
    assert response.status_code == 200
    ids = {row["student"] for row in response.data["results"]}
    assert ids == {student_portal_user.student_profile.pk}


@pytest.mark.integration
def test_registrar_can_revoke_a_document(registrar, as_user, student):
    document = services.issue_certificate(student_id=student.pk, actor=registrar)
    response = as_user(registrar).post(
        f"{ISSUED_URL}{document.pk}/revoke/", {"reason": "Printed in error"}, format="json"
    )
    assert response.status_code == 200
    assert response.data["is_revoked"] is True


@pytest.mark.integration
def test_verification_is_public(api, registrar, student):
    document = services.issue_certificate(student_id=student.pk, actor=registrar)
    response = api.get(f"/api/v1/documents/verify/{document.serial_number}/")
    assert response.status_code == 200
    assert response.data["is_valid"] is True


@pytest.mark.integration
def test_verifying_an_unknown_serial_returns_404(api):
    response = api.get("/api/v1/documents/verify/CERT/2020/99999/")
    assert response.status_code == 404


@pytest.mark.integration
def test_a_student_can_check_their_own_clearance(student_portal_user, as_user):
    response = as_user(student_portal_user).get(
        f"/api/v1/documents/students/{student_portal_user.student_profile.pk}/clearance/"
    )
    assert response.status_code == 200
    assert response.data["clear"] is True


@pytest.mark.integration
def test_a_student_cannot_check_another_students_clearance(
    student_portal_user, as_user, programme, curriculum_version, academic_year
):
    from apps.registry.models import Gender
    from apps.registry.services import create_student

    other_student = create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Other",
        last_name="Graduate",
        gender=Gender.FEMALE,
        curriculum_version_id=curriculum_version.pk,
        reason="test",
    )
    response = as_user(student_portal_user).get(
        f"/api/v1/documents/students/{other_student.pk}/clearance/"
    )
    assert response.status_code == 403
