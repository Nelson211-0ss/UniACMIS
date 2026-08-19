from __future__ import annotations

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import error_envelope
from apps.core.permissions import HasModulePermission
from apps.reporting import services
from apps.reporting.models import DashboardWidget
from apps.reporting.serializers import DashboardWidgetSerializer, PassRateQuerySerializer


class DashboardWidgetViewSet(viewsets.ModelViewSet):
    """Which KPI tiles a management-tier user sees, and in what order —
    editable data, not a page a developer redeploys to change."""

    queryset = DashboardWidget.objects.all()
    serializer_class = DashboardWidgetSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "SAFE": "reporting.view_dashboardwidget",
        "POST": "reporting.add_dashboardwidget",
        "PUT": "reporting.change_dashboardwidget",
        "PATCH": "reporting.change_dashboardwidget",
        "DELETE": "reporting.delete_dashboardwidget",
    }


class DashboardView(APIView):
    permission_classes = [HasModulePermission]
    required_permission = "reporting.view_dashboard"

    @extend_schema(summary="KPI dashboard — enabled widgets and their data")
    def get(self, request: Request) -> Response:
        return Response(services.dashboard_data())


class PassRateReportView(APIView):
    permission_classes = [HasModulePermission]
    required_permission = "reporting.view_dashboard"

    @extend_schema(
        summary="Pass rate for one course in one semester", parameters=[PassRateQuerySerializer]
    )
    def get(self, request: Request) -> Response:
        query = PassRateQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        report = services.pass_rate_report(
            course_id=query.validated_data["course"], semester_id=query.validated_data["semester"]
        )
        return Response(report)


class ReportExportView(APIView):
    """FR-RPT-02/05. CSV and Excel are built from the standard library and a
    pure-Python dependency respectively; PDF stays out of scope for the same
    reason D-8 (`docs/TRACEABILITY.md`) keeps a printed timetable an HTML
    page rather than a rendered file — no PDF renderer's system libraries
    are in this image."""

    permission_classes = [HasModulePermission]
    required_permission = "reporting.export_statutoryreport"

    @extend_schema(summary="Export a report as CSV or Excel")
    def get(self, request: Request, key: str) -> Response | HttpResponse:
        # Deliberately not "format" — DRF reserves that query parameter for its
        # own content-negotiation and raises a bare 404 before this method
        # ever runs if it doesn't match a registered renderer.
        export_format = request.query_params.get("export_format", "csv")
        if export_format not in {"csv", "xlsx"}:
            return Response(
                error_envelope("invalid_format", "export_format must be 'csv' or 'xlsx'."),
                status=400,
            )

        params = {k: v for k, v in request.query_params.items() if k != "export_format"}
        rows = services.report_rows(key, params)

        if export_format == "csv":
            response = HttpResponse(services.rows_to_csv(rows), content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="{key}.csv"'
        else:
            response = HttpResponse(
                services.rows_to_xlsx(rows),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Content-Disposition"] = f'attachment; filename="{key}.xlsx"'
        return response
