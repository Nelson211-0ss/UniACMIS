"""Reporting & compliance services (FR-RPT-01…05).

Both the dashboard and the report catalog below are fixed, documented
functions rather than a data-driven query-building engine — the same
"detection over generation" scope line Phase 3 drew for timetabling
(`docs/TRACEABILITY.md` D-3/D-7/D-15): a small set of correct, explainable
reports beats a generic report builder nobody has asked to configure yet.
Which dashboard tiles are *visible* is still real configuration
(`DashboardWidget`), per `NFR-MAINT-03`.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from openpyxl import Workbook

from apps.core.exceptions import DomainError
from apps.reporting.models import DashboardWidget


class UnknownReport(DomainError):
    code = "unknown_report"
    status_code = 404


class MissingReportParameter(DomainError):
    code = "missing_report_parameter"


def _as_int(params: dict[str, Any], name: str) -> int | None:
    value = params.get(name)
    return int(value) if value not in (None, "") else None


def _enrollment_rows(params: dict[str, Any]) -> list[dict[str, Any]]:
    from apps.registry.services import student_register

    return student_register(academic_year_id=_as_int(params, "academic_year"))


def _defaulters_rows(params: dict[str, Any]) -> list[dict[str, Any]]:
    from apps.finance.services import defaulter_report

    rows = defaulter_report(semester_id=_as_int(params, "semester"))
    return [{**row, "balance": str(row["balance"])} for row in rows]


def _pass_rate_rows(params: dict[str, Any]) -> list[dict[str, Any]]:
    course_id = _as_int(params, "course")
    semester_id = _as_int(params, "semester")
    if course_id is None or semester_id is None:
        raise MissingReportParameter("Both 'course' and 'semester' are required.")
    return pass_rate_report(course_id=course_id, semester_id=semester_id)["rows"]


REPORT_CATALOG: dict[str, dict[str, Any]] = {
    "student_register": {
        "label": "Student register (disaggregated)",
        "rows": _enrollment_rows,
    },
    "defaulters": {
        "label": "Fee defaulters",
        "rows": _defaulters_rows,
    },
    "pass_rate": {
        "label": "Course pass rate (by student)",
        "rows": _pass_rate_rows,
    },
}


def dashboard_data() -> list[dict[str, Any]]:
    """FR-RPT-01: each enabled widget, in its configured order, with its
    computed KPI payload."""
    from apps.finance.services import revenue_summary
    from apps.registry.services import enrollment_counts, staff_student_ratio

    computed = {
        "enrollment": enrollment_counts,
        "revenue": revenue_summary,
        "ratios": staff_student_ratio,
    }
    widgets = DashboardWidget.objects.filter(is_enabled=True).order_by("sort_order", "key")
    return [
        {"key": widget.key, "label": widget.label, "data": computed[widget.key]()}
        for widget in widgets
        if widget.key in computed
    ]


def pass_rate_report(*, course_id: int, semester_id: int) -> dict[str, Any]:
    """FR-RPT-01's "pass rates", for one course in one semester — every
    other module already answers "how did this registration do?"
    (`examinations.course_result`); this is that question asked for every
    registration in the course at once."""
    from apps.enrollment.services import active_registration_ids
    from apps.examinations.services import course_result

    passed = failed = incomplete = 0
    rows = []
    for registration_id in active_registration_ids(course_id, semester_id):
        result = course_result(registration_id)
        if result["is_pass"] is None:
            incomplete += 1
        elif result["is_pass"]:
            passed += 1
        else:
            failed += 1
        rows.append(
            {
                "registration_id": registration_id,
                "percent": result["percent"],
                "letter": result["letter"],
                "is_pass": result["is_pass"],
            }
        )

    graded = passed + failed
    return {
        "course_id": course_id,
        "semester_id": semester_id,
        "passed": passed,
        "failed": failed,
        "incomplete": incomplete,
        "pass_rate_percent": round(passed / graded * 100, 1) if graded else None,
        "rows": rows,
    }


def report_rows(key: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    entry = REPORT_CATALOG.get(key)
    if entry is None:
        raise UnknownReport(f"No report named '{key}'.")
    return entry["rows"](params)


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def rows_to_xlsx(rows: list[dict[str, Any]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    if rows:
        sheet.append(list(rows[0].keys()))
        for row in rows:
            sheet.append([str(value) if value is not None else "" for value in row.values()])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
