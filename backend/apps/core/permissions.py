"""
The single authorisation enforcement point for the API.

Views declare *what permission they need*; this class checks it. Role-name string
comparisons scattered through views are how authorisation logic rots, so there
are none anywhere in this codebase.

Declaration is mandatory and fails closed. A view that declares nothing is
denied, not opened — and `tests/test_permission_matrix.py` asserts that every
registered API view declares the attribute at all, so forgetting it breaks CI
rather than shipping an open endpoint.

    class StudentViewSet(ModelViewSet):
        permission_classes = [HasModulePermission]
        required_permissions = {
            "GET": "registry.view_student",
            "POST": "registry.add_student",
            "PUT": "registry.change_student",
            "PATCH": "registry.change_student",
            "DELETE": "registry.delete_student",
        }

    class MeView(APIView):
        required_permission = None   # authenticated, no specific permission
"""

from __future__ import annotations

import logging
from typing import Any

from rest_framework.permissions import SAFE_METHODS, BasePermission

logger = logging.getLogger(__name__)

UNSET = object()


class HasModulePermission(BasePermission):
    message = "You do not have permission to perform this action."

    def _required(self, request: Any, view: Any) -> Any:
        by_method = getattr(view, "required_permissions", None)
        if isinstance(by_method, dict):
            if request.method in by_method:
                return by_method[request.method]
            if request.method in SAFE_METHODS and "SAFE" in by_method:
                return by_method["SAFE"]
            if "*" in by_method:
                return by_method["*"]
            # Declared a map that omits this method: deny it deliberately.
            return UNSET

        return getattr(view, "required_permission", UNSET)

    def has_permission(self, request: Any, view: Any) -> bool:
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return False
        if not getattr(user, "is_active", False):
            return False

        required = self._required(request, view)

        if required is UNSET:
            logger.error(
                "%s declares no required_permission(s); denying %s. "
                "Declare one, or `required_permission = None` for authenticated-only.",
                view.__class__.__name__,
                request.method,
            )
            return False

        if required is None:
            return True

        codenames = [required] if isinstance(required, str) else list(required)
        return all(user.has_perm(codename) for codename in codenames)

    def has_object_permission(self, request: Any, view: Any, obj: Any) -> bool:
        # Row-level narrowing is the queryset's job (see accounts.mixins);
        # object hooks that need more can override this per view.
        return True


class IsAuthenticatedAndActive(BasePermission):
    """For endpoints that need a live session but no specific permission."""

    def has_permission(self, request: Any, view: Any) -> bool:
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and user.is_active)
