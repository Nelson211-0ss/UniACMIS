"""Library API: the catalogue is public to any authenticated user; only
library staff catalogue items or run circulation; a borrower sees only their
own loans (FR-LIB-01…03)."""

from __future__ import annotations

import pytest

from apps.library.models import ItemType

pytestmark = pytest.mark.django_db

ITEMS_URL = "/api/v1/library/items/"
LOANS_URL = "/api/v1/library/loans/"


@pytest.fixture
def item(librarian, as_user):
    response = as_user(librarian).post(
        ITEMS_URL,
        {
            "title": "Introduction to Structural Engineering",
            "item_type": ItemType.BOOK,
            "total_copies": 2,
        },
        format="json",
    )
    assert response.status_code == 201
    return response.data


@pytest.mark.integration
def test_the_catalogue_is_unreachable_when_not_authenticated(api):
    response = api.get(ITEMS_URL)
    assert response.status_code in {401, 403}


@pytest.mark.integration
def test_any_authenticated_role_can_browse_the_catalogue(lecturer, as_user, item):
    response = as_user(lecturer).get(ITEMS_URL)
    assert response.status_code == 200
    assert any(row["id"] == item["id"] for row in response.data["results"])


@pytest.mark.integration
def test_only_library_staff_can_catalogue_an_item(lecturer, as_user):
    response = as_user(lecturer).post(
        ITEMS_URL,
        {"title": "Should be rejected", "item_type": ItemType.BOOK, "total_copies": 1},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_an_electronic_item_without_a_url_is_rejected(librarian, as_user):
    response = as_user(librarian).post(
        ITEMS_URL,
        {
            "title": "E-journal",
            "item_type": ItemType.EBOOK,
            "is_electronic": True,
            "total_copies": 1,
        },
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.integration
def test_library_staff_can_check_out_an_item_to_a_student(librarian, as_user, item, student):
    response = as_user(librarian).post(
        f"{LOANS_URL}checkout/", {"item": item["id"], "borrower_student": student.pk}, format="json"
    )
    assert response.status_code == 201
    assert response.data["status"] == "active"


@pytest.mark.integration
def test_a_lecturer_cannot_check_out_an_item(lecturer, as_user, item, student):
    response = as_user(lecturer).post(
        f"{LOANS_URL}checkout/", {"item": item["id"], "borrower_student": student.pk}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_a_student_only_sees_their_own_loans(
    librarian, as_user, item, student, student_portal_user
):
    as_user(librarian).post(
        f"{LOANS_URL}checkout/", {"item": item["id"], "borrower_student": student.pk}, format="json"
    )

    response = as_user(student_portal_user).get(LOANS_URL)
    assert response.status_code == 200
    assert {row["borrower_student"] for row in response.data["results"]} == {student.pk}


@pytest.mark.integration
def test_returning_and_waiving_a_fine(librarian, as_user, item, student):
    checkout = as_user(librarian).post(
        f"{LOANS_URL}checkout/", {"item": item["id"], "borrower_student": student.pk}, format="json"
    )
    loan_id = checkout.data["id"]

    returned = as_user(librarian).post(f"{LOANS_URL}{loan_id}/return-loan/")
    assert returned.status_code == 200
    assert returned.data["status"] == "returned"

    waived = as_user(librarian).post(
        f"{LOANS_URL}{loan_id}/waive-fine/",
        {"reason": "Library was closed for renovation"},
        format="json",
    )
    assert waived.status_code == 200
    assert waived.data["fine_waived"] is True


@pytest.mark.integration
def test_a_lecturer_cannot_waive_a_fine(librarian, as_user, lecturer, item, student):
    checkout = as_user(librarian).post(
        f"{LOANS_URL}checkout/", {"item": item["id"], "borrower_student": student.pk}, format="json"
    )
    loan_id = checkout.data["id"]

    response = as_user(lecturer).post(
        f"{LOANS_URL}{loan_id}/waive-fine/", {"reason": "Not my call to make"}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_marking_a_loan_lost(librarian, as_user, item, student):
    checkout = as_user(librarian).post(
        f"{LOANS_URL}checkout/", {"item": item["id"], "borrower_student": student.pk}, format="json"
    )
    loan_id = checkout.data["id"]

    response = as_user(librarian).post(f"{LOANS_URL}{loan_id}/mark-lost/")
    assert response.status_code == 200
    assert response.data["status"] == "lost"
