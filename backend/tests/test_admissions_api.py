"""
Admissions API: applicant self-service scoping vs. registrar's full authority
(FR-ADM-01…08), and that the sensitive actions (decide, convert, merit list)
demand the one permission that actually authorises them.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.admissions import services
from apps.admissions.models import ApplicationStatus
from apps.registry.models import Gender

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/admissions/applications/"


@pytest.fixture
def applicant(roles, user_factory):
    return user_factory(role="applicant", email="applicant@test.ss")


@pytest.fixture
def own_application(applicant, programme, academic_year):
    return services.create_application(
        programme_id=programme.pk,
        intended_academic_year_id=academic_year.pk,
        first_name="Own",
        last_name="Applicant",
        gender=Gender.FEMALE,
        phone="+211920000002",
        applicant_user=applicant,
    )


@pytest.fixture
def someone_elses_application(programme, academic_year, user_factory):
    other = user_factory(email="other-applicant@test.ss")
    return services.create_application(
        programme_id=programme.pk,
        intended_academic_year_id=academic_year.pk,
        first_name="Someone",
        last_name="Else",
        gender=Gender.MALE,
        applicant_user=other,
    )


# ------------------------------------------------------------------- scoping


@pytest.mark.integration
def test_an_applicant_sees_only_their_own_application(
    applicant, own_application, someone_elses_application, as_user
):
    response = as_user(applicant).get(LIST_URL)
    assert response.status_code == 200
    ids = {row["id"] for row in response.data["results"]}
    assert ids == {own_application.pk}


@pytest.mark.integration
def test_the_registrar_sees_every_application(
    registrar, own_application, someone_elses_application, as_user
):
    response = as_user(registrar).get(LIST_URL)
    assert response.status_code == 200
    ids = {row["id"] for row in response.data["results"]}
    assert {own_application.pk, someone_elses_application.pk} <= ids


@pytest.mark.integration
def test_an_applicant_cannot_fetch_someone_elses_application_by_id(
    applicant, someone_elses_application, as_user
):
    response = as_user(applicant).get(f"{LIST_URL}{someone_elses_application.pk}/")
    assert response.status_code == 404  # scoped out entirely, not merely forbidden


@pytest.mark.integration
def test_a_lecturer_has_no_admissions_access(roles, staff_factory, as_user):
    lecturer = staff_factory("lecturer", email="lect-adm@test.ss")
    response = as_user(lecturer).get(LIST_URL)
    assert response.status_code == 403


# --------------------------------------------------------------------- create


@pytest.mark.integration
def test_an_applicant_can_submit_their_own_application(
    applicant, programme, academic_year, as_user
):
    payload = {
        "programme": programme.pk,
        "intended_academic_year": academic_year.pk,
        "first_name": "New",
        "last_name": "Applicant",
        "gender": "female",
        "phone": "+211920000003",
    }
    response = as_user(applicant).post(LIST_URL, payload, format="json")
    assert response.status_code == 201
    assert response.data["reference_number"].startswith("APP/")


@pytest.mark.integration
def test_a_created_application_is_tagged_with_its_source(
    applicant, registrar, programme, academic_year, as_user
):
    self_service = as_user(applicant).post(
        LIST_URL,
        {
            "programme": programme.pk,
            "intended_academic_year": academic_year.pk,
            "first_name": "A",
            "last_name": "B",
            "gender": "female",
        },
        format="json",
    )
    staff_entry = as_user(registrar).post(
        LIST_URL,
        {
            "programme": programme.pk,
            "intended_academic_year": academic_year.pk,
            "first_name": "C",
            "last_name": "D",
            "gender": "male",
        },
        format="json",
    )

    from apps.admissions.models import Application

    assert Application.objects.get(pk=self_service.data["id"]).source == "self_service"
    assert Application.objects.get(pk=staff_entry.data["id"]).source == "staff_entry"


@pytest.mark.integration
def test_a_lecturer_cannot_create_an_application(
    roles, staff_factory, programme, academic_year, as_user
):
    lecturer = staff_factory("lecturer", email="lect-adm2@test.ss")
    response = as_user(lecturer).post(
        LIST_URL,
        {
            "programme": programme.pk,
            "intended_academic_year": academic_year.pk,
            "first_name": "X",
            "last_name": "Y",
            "gender": "male",
        },
        format="json",
    )
    assert response.status_code == 403


# ----------------------------------------------------------------------- edit


@pytest.mark.integration
def test_a_draft_application_can_be_edited_by_its_owner(applicant, own_application, as_user):
    response = as_user(applicant).patch(
        f"{LIST_URL}{own_application.pk}/", {"county": "Juba County"}, format="json"
    )
    assert response.status_code == 200
    assert response.data["county"] == "Juba County"


@pytest.mark.integration
def test_a_submitted_application_cannot_be_edited_directly(applicant, own_application, as_user):
    own_application.fee_paid = True
    own_application.save()
    services.submit_application(own_application)

    response = as_user(applicant).patch(
        f"{LIST_URL}{own_application.pk}/", {"county": "Changed"}, format="json"
    )
    assert response.status_code == 400
    assert response.data["error"]["code"] == "not_editable"


# ------------------------------------------------------------------- actions


@pytest.mark.integration
def test_only_a_registrar_can_decide_an_application(applicant, own_application, as_user):
    own_application.fee_paid = True
    own_application.save()
    services.submit_application(own_application)

    response = as_user(applicant).post(
        f"{LIST_URL}{own_application.pk}/decide/",
        {"decision": "offered", "reason": "Trying to self-approve"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_a_registrar_can_offer_and_the_applicant_can_accept(
    registrar, applicant, own_application, as_user
):
    own_application.fee_paid = True
    own_application.save()
    services.submit_application(own_application)

    decide = as_user(registrar).post(
        f"{LIST_URL}{own_application.pk}/decide/",
        {"decision": "offered", "reason": "Strong application"},
        format="json",
    )
    assert decide.status_code == 200
    assert decide.data["status"] == "offered"

    accept = as_user(applicant).post(f"{LIST_URL}{own_application.pk}/accept-offer/")
    assert accept.status_code == 200
    assert accept.data["status"] == "accepted"


@pytest.mark.integration
def test_only_a_registrar_can_convert_an_accepted_application(
    registrar, applicant, own_application, as_user
):
    own_application.fee_paid = True
    own_application.save()
    services.submit_application(own_application)
    services.decide_application(
        own_application,
        ApplicationStatus.OFFERED,
        decided_by=registrar,
        reason="Strong application",
    )
    services.accept_offer(own_application)

    denied = as_user(applicant).post(f"{LIST_URL}{own_application.pk}/convert/")
    assert denied.status_code == 403

    allowed = as_user(registrar).post(f"{LIST_URL}{own_application.pk}/convert/")
    assert allowed.status_code == 200
    assert "student_id" in allowed.data


@pytest.mark.integration
def test_the_merit_list_requires_decision_authority(
    registrar, applicant, programme, academic_year, as_user
):
    denied = as_user(applicant).get(
        f"/api/v1/admissions/merit-list/?programme={programme.pk}&academic_year={academic_year.pk}"
    )
    assert denied.status_code == 403

    allowed = as_user(registrar).get(
        f"/api/v1/admissions/merit-list/?programme={programme.pk}&academic_year={academic_year.pk}"
    )
    assert allowed.status_code == 200


@pytest.mark.integration
def test_merit_list_reflects_real_submitted_applications(
    registrar, programme, academic_year, as_user, user_factory
):
    for name, score in [("Top", "90"), ("Middle", "70"), ("Bottom", "40")]:
        applicant_user = user_factory(email=f"{name.lower()}@test.ss")
        application = services.create_application(
            programme_id=programme.pk,
            intended_academic_year_id=academic_year.pk,
            first_name=name,
            last_name="Candidate",
            gender=Gender.FEMALE,
            phone="+211900000000",
            applicant_user=applicant_user,
        )
        application.fee_paid = True
        application.save()
        services.submit_application(application)
        services.record_review(application, reviewer=registrar, score=Decimal(score))

    response = as_user(registrar).get(
        f"/api/v1/admissions/merit-list/?programme={programme.pk}&academic_year={academic_year.pk}"
    )
    assert response.status_code == 200
    names = [row["full_name"] for row in response.data]
    assert names == ["Top Candidate", "Middle Candidate", "Bottom Candidate"]
