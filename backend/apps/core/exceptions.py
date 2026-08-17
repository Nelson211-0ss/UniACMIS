"""
Domain exceptions and the single API error shape.

Every error the API returns has the same envelope, carrying a `request_id` that
also appears on audit rows and in the server log. A user's screenshot is then
enough to locate exactly what happened — which matters when the user is a
registrar on a bad connection describing a problem over the phone.

    {"error": {"code": "...", "message": "...", "details": {...}, "request_id": "..."}}
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.core import context

logger = logging.getLogger(__name__)


class DomainError(Exception):
    """Base for business-rule failures — expected outcomes, not bugs."""

    code = "domain_error"
    message = "The request could not be completed."
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        super().__init__(self.message)


class BlockedByHold(DomainError):
    """A hold prevents the operation (FR-ENR-03, FR-EXM-06, FR-DOC-04)."""

    code = "blocked_by_hold"
    message = "This action is blocked by an outstanding hold."
    status_code = status.HTTP_409_CONFLICT


class ConflictError(DomainError):
    code = "conflict"
    message = "The request conflicts with the current state of the record."
    status_code = status.HTTP_409_CONFLICT


class ConfigurationError(DomainError):
    """Institutional configuration is missing or invalid — e.g. no current
    academic year, or a grading scale with a gap in its bands."""

    code = "configuration_error"
    message = "The system is not configured for this operation yet."
    status_code = status.HTTP_409_CONFLICT


class SyncConflictDetected(Exception):
    """Raised by a sync handler whose entity is FLAG_FOR_REVIEW when the incoming
    write diverges from the stored value. The engine turns this into a
    `SyncConflict` row; nothing is overwritten."""

    def __init__(
        self,
        *,
        field_name: str,
        server_value: Any,
        client_value: Any,
        server_updated_at: Any | None = None,
        target: Any | None = None,
        message: str = "",
    ) -> None:
        self.field_name = field_name
        self.server_value = server_value
        self.client_value = client_value
        self.server_updated_at = server_updated_at
        self.target = target
        self.message = message or (
            f"Concurrent change to {field_name}; held for review rather than overwritten."
        )
        super().__init__(self.message)


def error_envelope(
    code: str, message: str, details: Any = None, request_id: str | None = None
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id or context.get_request_id() or "",
        }
    }


def _code_for(exc: Any, response_status: int) -> str:
    detail_code = getattr(getattr(exc, "detail", None), "code", None)
    if isinstance(detail_code, str):
        return detail_code
    default_code = getattr(exc, "default_code", None)
    if isinstance(default_code, str):
        return default_code
    return {
        400: "bad_request",
        401: "not_authenticated",
        403: "permission_denied",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        429: "throttled",
    }.get(response_status, "error")


def api_exception_handler(exc: Exception, context_dict: dict[str, Any]) -> Response | None:
    """DRF `EXCEPTION_HANDLER`. Normalises everything into one envelope."""

    # Business-rule failures raised by services.
    if isinstance(exc, DomainError):
        return Response(
            error_envelope(exc.code, exc.message, exc.details),
            status=exc.status_code,
        )

    # Model/full_clean validation surfacing through a view.
    if isinstance(exc, DjangoValidationError):
        details = (
            exc.message_dict
            if hasattr(exc, "message_dict")
            else {"non_field_errors": list(exc.messages)}
        )
        return Response(
            error_envelope("validation_error", "The submitted data is not valid.", details),
            status=status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(exc, DjangoPermissionDenied):
        return Response(
            error_envelope("permission_denied", "You do not have permission to do this."),
            status=status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, Http404):
        return Response(error_envelope("not_found", "Not found."), status=status.HTTP_404_NOT_FOUND)

    response = drf_exception_handler(exc, context_dict)
    if response is None:
        # Unhandled: log with the request id so the trail is findable, and do not
        # leak the internals to the client.
        logger.exception("Unhandled exception (request_id=%s)", context.get_request_id())
        return None

    detail = response.data
    code = _code_for(exc, response.status_code)

    if isinstance(detail, dict) and "detail" in detail and len(detail) == 1:
        message, details = str(detail["detail"]), {}
    elif isinstance(detail, dict):
        message, details = "The submitted data is not valid.", detail
    elif isinstance(detail, list):
        message, details = "The submitted data is not valid.", {"non_field_errors": detail}
    else:
        message, details = str(detail), {}

    response.data = error_envelope(code, message, details)
    return response
