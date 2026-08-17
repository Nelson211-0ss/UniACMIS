"""Infrastructure endpoints."""

from __future__ import annotations

from typing import Any

from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """Unauthenticated liveness probe.

    Deliberately checks the database rather than just returning 200: on a campus
    box the interesting failure is Postgres not coming back up after a power cut,
    and a monitor that only pings the web tier would call that healthy.
    """

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        summary="Service health",
        responses={200: dict, 503: dict},
        auth=[],
    )
    def get(self, request: Request) -> Response:
        checks: dict[str, str] = {}
        healthy = True

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            checks["database"] = "ok"
        except Exception as exc:  # pragma: no cover - exercised by taking the DB down
            checks["database"] = f"error: {exc.__class__.__name__}"
            healthy = False

        return Response(
            {"status": "ok" if healthy else "degraded", "checks": checks},
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
