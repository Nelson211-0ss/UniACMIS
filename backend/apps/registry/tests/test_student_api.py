"""
Student creation through the API.

Regression coverage for a bug caught while building Phase 2: DRF's default
`create()` re-serializes the new instance through the same (deliberately
narrow) input serializer, so the response silently omitted the generated
`student_id` — exactly the field a caller creating a student most needs back.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/registry/students/"


@pytest.mark.integration
def test_creating_a_student_returns_the_generated_student_id(
    registrar, programme, academic_year, as_user
):
    response = as_user(registrar).post(
        LIST_URL,
        {
            "programme": programme.pk,
            "entry_academic_year": academic_year.pk,
            "first_name": "Api",
            "last_name": "Created",
            "gender": "female",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["student_id"]
    assert response.data["full_name"] == "Api Created"
