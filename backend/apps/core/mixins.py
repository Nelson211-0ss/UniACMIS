"""Reusable DRF view and serializer mixins."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.response import Response


class ModelCleanSerializerMixin:
    """Run the model's own `clean()` as part of serializer validation.

    `ModelSerializer` never calls `full_clean()`, so any rule expressed in a
    model's `clean()` — a prerequisite cycle, an elective with no group, a band
    on a locked grading scale — is enforced by the Django admin and by services
    that call `full_clean()` explicitly, but silently skipped by a plain API
    write. Where the model is the only place a rule lives, mix this in.

    Validating *before* the write matters: a rule that is also a database
    constraint (a self-referencing prerequisite, say) would otherwise surface as
    an IntegrityError 500 rather than the model's own readable message, because
    the insert fails before any after-the-fact check could run.
    """

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)  # type: ignore[misc]

        # Merge over the existing row for a PATCH, so a partial update is
        # validated as the record it would become rather than in isolation.
        instance = self.instance  # type: ignore[attr-defined]
        model = self.Meta.model  # type: ignore[attr-defined]
        if instance is None:
            candidate = model(**attrs)
        else:
            candidate = model(pk=instance.pk)
            for field in model._meta.concrete_fields:
                setattr(candidate, field.attname, getattr(instance, field.attname))
            for name, value in attrs.items():
                setattr(candidate, name, value)

        try:
            candidate.clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                error.message_dict
                if hasattr(error, "message_dict")
                else {"non_field_errors": list(error.messages)}
            ) from error

        return attrs


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
