"""Reporting API: management reads the dashboard and exports reports; only
ICT admin configures which widgets are visible (FR-RPT-01…05)."""

from __future__ import annotations

import pytest

from apps.reporting.models import DashboardWidget

pytestmark = pytest.mark.django_db

DASHBOARD_URL = "/api/v1/reporting/dashboard/"
WIDGETS_URL = "/api/v1/reporting/widgets/"


@pytest.mark.integration
def test_management_can_view_the_dashboard(management_officer, as_user, student):
    DashboardWidget.objects.create(key="enrollment", label="Enrollment", is_enabled=True)
    response = as_user(management_officer).get(DASHBOARD_URL)
    assert response.status_code == 200
    assert response.data[0]["key"] == "enrollment"


@pytest.mark.integration
def test_a_lecturer_cannot_view_the_dashboard(lecturer, as_user):
    response = as_user(lecturer).get(DASHBOARD_URL)
    assert response.status_code == 403


@pytest.mark.integration
def test_ict_admin_can_configure_widgets(ict_admin, as_user):
    response = as_user(ict_admin).post(
        WIDGETS_URL,
        {"key": "revenue", "label": "Revenue", "is_enabled": True, "sort_order": 2},
        format="json",
    )
    assert response.status_code == 201


@pytest.mark.integration
def test_management_cannot_configure_widgets(management_officer, as_user):
    response = as_user(management_officer).post(
        WIDGETS_URL, {"key": "revenue", "label": "Revenue", "is_enabled": True}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.integration
def test_exporting_the_student_register_as_csv(management_officer, as_user, student):
    response = as_user(management_officer).get(
        "/api/v1/reporting/reports/student_register/export/?export_format=csv"
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert student.student_id in response.content.decode()


@pytest.mark.integration
def test_exporting_as_excel(management_officer, as_user, student):
    response = as_user(management_officer).get(
        "/api/v1/reporting/reports/student_register/export/?export_format=xlsx"
    )
    assert response.status_code == 200
    assert response["Content-Type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@pytest.mark.integration
def test_an_invalid_export_format_is_rejected(management_officer, as_user):
    response = as_user(management_officer).get(
        "/api/v1/reporting/reports/student_register/export/?export_format=pdf"
    )
    assert response.status_code == 400


@pytest.mark.integration
def test_a_lecturer_cannot_export_reports(lecturer, as_user):
    response = as_user(lecturer).get(
        "/api/v1/reporting/reports/student_register/export/?export_format=csv"
    )
    assert response.status_code == 403
