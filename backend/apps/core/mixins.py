"""Reusable DRF view mixins."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.response import Response


class CreateWithResponseSerializerMixin:
    """Validate a create request with one serializer, respond with another.

    DRF's default `CreateModelMixin.create()` re-serializes the new instance
    through the *same* serializer class used for input. Where the input
    serializer is deliberately narrow (a "create" shape that excludes
    server-generated fields — an auto ID, a computed status), the response then
    silently omits exactly the fields a caller most needs back. Declare
    `response_serializer_class` and the create response reflects the full
    record instead.
    """

    response_serializer_class: type | None = None

    def create(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        response_class = self.response_serializer_class or serializer.__class__
        output = response_class(serializer.instance, context=self.get_serializer_context())
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)
