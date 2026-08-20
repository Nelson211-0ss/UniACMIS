"""Bulk student import, reachable from the browser (NFR-DATA-03).

`apps.registry.services.import_students` already has thorough row-level
coverage in `test_import_students.py`; this file only exercises the HTTP
layer wrapped around it — upload handling, permission, and the
dry-run/commit passthrough — so the two suites do not duplicate each other.
"""

from __future__ import annotations

import csv
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.registry.models import Student

pytestmark = pytest.mark.django_db

URL = "/api/v1/registry/students/bulk-import/"

FIELDS = ["first_name", "last_name", "gender", "programme_code", "entry_academic_year"]


def _csv_file(rows: list[dict[str, str]], name: str = "students.csv") -> SimpleUploadedFile:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return SimpleUploadedFile(name, buf.getvalue().encode("utf-8"), content_type="text/csv")


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "first_name": "Legacy",
        "last_name": "Student",
        "gender": "female",
        "programme_code": "CIV",
        "entry_academic_year": "2026/2027",
    }
    row.update(overrides)
    return row


@pytest.mark.integration
def test_a_dry_run_validates_but_writes_nothing(registrar, programme, academic_year, as_user):
    response = as_user(registrar).post(URL, {"file": _csv_file([_row()])}, format="multipart")

    assert response.status_code == 200
    assert response.data == {"total": 1, "valid": 1, "created": 0, "errors": []}
    assert Student.objects.count() == 0


@pytest.mark.integration
def test_committing_writes_the_students(registrar, programme, academic_year, as_user):
    rows = [_row(first_name="First"), _row(first_name="Second")]
    response = as_user(registrar).post(
        URL, {"file": _csv_file(rows), "commit": "true"}, format="multipart"
    )

    assert response.status_code == 200
    assert response.data["created"] == 2
    assert Student.objects.count() == 2


@pytest.mark.integration
def test_an_invalid_row_is_reported_and_nothing_is_written(
    registrar, programme, academic_year, as_user
):
    rows = [_row(), _row(programme_code="NOPE")]
    response = as_user(registrar).post(
        URL, {"file": _csv_file(rows), "commit": "true"}, format="multipart"
    )

    assert response.status_code == 200
    assert response.data["created"] == 0
    assert len(response.data["errors"]) == 1
    assert response.data["errors"][0]["row"] == 2
    assert Student.objects.count() == 0


@pytest.mark.integration
def test_a_student_may_not_bulk_import(student_portal_user, as_user):
    response = as_user(student_portal_user).post(
        URL, {"file": _csv_file([_row()])}, format="multipart"
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_no_file_is_a_client_error(registrar, as_user):
    response = as_user(registrar).post(URL, {}, format="multipart")
    assert response.status_code == 400


@pytest.mark.integration
def test_a_header_only_file_is_rejected(registrar, as_user):
    response = as_user(registrar).post(URL, {"file": _csv_file([])}, format="multipart")
    assert response.status_code == 400
    assert response.data["error"]["code"] == "empty_file"
