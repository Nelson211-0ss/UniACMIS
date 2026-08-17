"""
Row-level scoping (NFR-SEC-01, least privilege).

A permission answers "may this user read student records at all?". It cannot
answer "which ones?" — and a lecturer who can list all 20,000 students because
they hold `registry.view_student` is a privacy problem even though the permission
check passed.

Views declare, per role, how to narrow their queryset:

    class StudentViewSet(ScopedQuerysetMixin, ModelViewSet):
        unscoped_roles = {"registrar", "ict_admin", "management"}
        scope_methods = {"lecturer": "scope_for_lecturer", "student": "scope_for_self"}

        def scope_for_lecturer(self, qs, user): ...
        def scope_for_self(self, qs, user): ...

Fails closed: a user whose roles match no rule and who is not listed as unscoped
gets an empty queryset, not everything.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import QuerySet

logger = logging.getLogger(__name__)


class ScopedQuerysetMixin:
    #: Roles that legitimately see every row for this view.
    unscoped_roles: set[str] = set()

    #: role code → name of a method on the view: (queryset, user) -> queryset
    scope_methods: dict[str, str] = {}

    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset()  # type: ignore[misc]
        user = getattr(self.request, "user", None)  # type: ignore[attr-defined]

        if user is None or not user.is_authenticated:
            return queryset.none()

        # A superuser is an ICT break-glass account, and its reads are audited.
        if user.is_superuser:
            return queryset

        role_codes = set(user.role_codes())

        if role_codes & self.unscoped_roles:
            return queryset

        for code in sorted(role_codes):
            method_name = self.scope_methods.get(code)
            if not method_name:
                continue
            method = getattr(self, method_name, None)
            if method is None:
                logger.error(
                    "%s maps role '%s' to missing method '%s'.",
                    self.__class__.__name__,
                    code,
                    method_name,
                )
                continue
            return method(queryset, user)

        logger.info(
            "%s: no scope rule for roles %s; returning an empty queryset.",
            self.__class__.__name__,
            sorted(role_codes) or ["<none>"],
        )
        return queryset.none()


class SensitiveReadAuditMixin:
    """Log reads of grade and financial records (NFR-SEC-03 requires logging
    *access*, not only modification).

    Applied on detail routes rather than lists: recording one entry per row of a
    200-row list would bury the trail it is meant to make searchable.
    """

    sensitive_read_description: str = ""

    def retrieve(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        response = super().retrieve(request, *args, **kwargs)  # type: ignore[misc]
        try:
            from apps.audit.services import record_sensitive_view

            record_sensitive_view(
                instance=self.get_object(),  # type: ignore[attr-defined]
                description=self.sensitive_read_description,
            )
        except Exception:  # pragma: no cover
            logger.exception("Failed to record sensitive read")
        return response
