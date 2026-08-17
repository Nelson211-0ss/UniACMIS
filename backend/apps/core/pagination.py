"""
Pagination defaults.

No list endpoint may return an unbounded result set — a registrar on a 2G
connection asking for "all students" must not be handed 20,000 rows
(NFR-PERF-01, NFR-PERF-03).
"""

from rest_framework.pagination import CursorPagination, PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Default for administrative lists, which need a total count to page
    through sensibly."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200


class LargeResultPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


class AppendOnlyCursorPagination(CursorPagination):
    """For append-only, high-volume tables such as the audit log: a COUNT(*) over
    millions of rows is the slowest part of the response, and nobody needs to
    jump to page 4,712."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
    ordering = "-created_at"
