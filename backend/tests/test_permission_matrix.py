"""
Authorisation coverage (NFR-SEC-01).

Two distinct guarantees:

1. **No endpoint ships unguarded.** Every API view must declare what permission it
   needs. This is introspective, so a view added in Phase 2 that forgets to
   declare one fails here rather than shipping open.
2. **Roles can reach what they should and nothing else**, checked as an actual
   role × endpoint matrix.

Plus separation of duties: no role may hold both grade-write and money-write
permissions.
"""

from __future__ import annotations

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.views import APIView

from apps.accounts.roles import (
    ADMISSIONS_SELF,
    GRADE_WRITE_PERMISSIONS,
    MONEY_WRITE_PERMISSIONS,
    ROLES,
    ROLES_BY_CODE,
)

pytestmark = pytest.mark.django_db


# Views that legitimately do not declare a module permission, with the reason.
# Adding to this list is a deliberate act that shows up in review.
EXEMPT_VIEWS = {
    "LoginView": "public — this is how you obtain a token",
    "RefreshView": "public — validated by the refresh token itself",
    "LogoutView": "any signed-in user may end their own session",
    "ChangePasswordView": "any signed-in user may change their own password",
    "MFASetupView": "any signed-in user may enrol their own account in MFA",
    "MFAConfirmView": "any signed-in user may confirm their own MFA enrolment",
    "MFADisableView": "any signed-in user may disable MFA on their own account",
    "HealthCheckView": "unauthenticated liveness probe for campus monitoring",
    "SpectacularAPIView": "schema document",
    "SpectacularSwaggerView": "schema UI",
    "SpectacularRedocView": "schema UI",
    "TokenVerifyView": "token validation",
    # DRF's router index. It only lists the routes the caller can already reach,
    # uses the default IsAuthenticated permission, and exposes no data of its own.
    "APIRootView": "router index — authenticated route listing, no data",
}


def _collect_api_views(patterns, prefix: str = "") -> list[tuple[str, type]]:
    found: list[tuple[str, type]] = []
    for entry in patterns:
        if isinstance(entry, URLResolver):
            found.extend(_collect_api_views(entry.url_patterns, prefix + str(entry.pattern)))
        elif isinstance(entry, URLPattern):
            view_class = getattr(entry.callback, "cls", None)
            if view_class is not None and issubclass(view_class, APIView):
                found.append((prefix + str(entry.pattern), view_class))
    return found


def _api_v1_views() -> dict[str, type]:
    all_views = _collect_api_views(get_resolver().url_patterns)
    return {
        view.__name__: view
        for route, view in all_views
        if route.startswith("api/v1/") or view.__name__ == "HealthCheckView"
    }


def test_every_api_view_declares_a_required_permission():
    """A view with no declaration is denied at runtime, but that is a silent
    failure discovered by a confused user. This makes it a loud one."""
    undeclared = []

    for name, view in sorted(_api_v1_views().items()):
        if name in EXEMPT_VIEWS:
            continue
        has_single = hasattr(view, "required_permission")
        has_map = hasattr(view, "required_permissions")
        if not (has_single or has_map):
            undeclared.append(name)

    assert not undeclared, (
        "These API views declare no required_permission(s) and would be denied for "
        f"everyone: {undeclared}. Declare one, or `required_permission = None` for "
        "authenticated-only, or add it to EXEMPT_VIEWS with a reason."
    )


def test_every_model_backed_view_uses_the_enforcement_class():
    """A view exposing a queryset must go through `HasModulePermission`.

    Without this, a view could satisfy the declaration test above while relying on
    the bare `IsAuthenticated` default — meaning any signed-in student could read
    it. This is the check that makes exempting `APIRootView` safe.
    """
    from apps.core.permissions import HasModulePermission

    unguarded = []
    for name, view in sorted(_api_v1_views().items()):
        if name in EXEMPT_VIEWS or not hasattr(view, "queryset"):
            continue
        if HasModulePermission not in getattr(view, "permission_classes", []):
            unguarded.append(name)

    assert not unguarded, (
        f"These data-exposing views do not use HasModulePermission: {unguarded}. "
        "They would fall back to authenticated-only, which any student satisfies."
    )


def test_the_api_surface_was_actually_discovered():
    """Guards the test above: if introspection silently found nothing, it would
    pass while checking naught."""
    views = _api_v1_views()
    assert len(views) >= 10, f"only found {sorted(views)}"
    assert "StudentViewSet" in views


def test_declared_permission_maps_cover_every_write_method():
    """A map that omits PATCH denies PATCH, which is safe but usually an
    oversight rather than a decision."""
    gaps = []
    for name, view in sorted(_api_v1_views().items()):
        mapping = getattr(view, "required_permissions", None)
        if not isinstance(mapping, dict):
            continue
        http_methods = {m.upper() for m in getattr(view, "http_method_names", [])}
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            # ViewSets get their methods from the router, so only a view that
            # clearly exposes a queryset is worth flagging.
            if (
                method in http_methods
                and method not in mapping
                and "*" not in mapping
                and hasattr(view, "queryset")
            ):
                gaps.append(f"{name}.{method}")
    # Reported rather than asserted-empty: some viewsets deliberately omit DELETE.
    for gap in gaps:
        assert gap.endswith(".DELETE"), f"{gap} is a write method with no declared permission"


# ----------------------------------------------------- separation of duties


def test_no_role_holds_both_grade_write_and_money_write():
    """The core separation of duties rule (NFR-SEC-01).

    Asserted against the policy in roles.py rather than the database, so it holds
    for the finance and examinations permissions that arrive in Phases 3 and 4.
    """
    violations = []
    for definition in ROLES:
        held = set(definition.permissions)
        grades = held & GRADE_WRITE_PERMISSIONS
        money = held & MONEY_WRITE_PERMISSIONS
        if grades and money:
            violations.append((definition.code, sorted(grades), sorted(money)))

    assert not violations, f"roles holding both grade-write and money-write: {violations}"


def test_ict_admin_holds_neither_grades_nor_money():
    """ICT administers accounts. Taking a grade or money permission requires
    granting themselves another role, which the audit trail records."""
    held = set(ROLES_BY_CODE["ict_admin"].permissions)
    assert not (held & GRADE_WRITE_PERMISSIONS)
    assert not (held & MONEY_WRITE_PERMISSIONS)


def test_finance_cannot_touch_marks():
    held = set(ROLES_BY_CODE["finance"].permissions)
    assert not any(p.startswith("examinations.") and p != "examinations.view_mark" for p in held)


def test_examinations_cannot_touch_money():
    held = set(ROLES_BY_CODE["examinations"].permissions)
    assert not (held & MONEY_WRITE_PERMISSIONS)


def test_result_approval_is_separate_from_result_processing():
    """FR-EXM-05: the office that prepares results must not also approve them."""
    examinations = set(ROLES_BY_CODE["examinations"].permissions)
    senate = set(ROLES_BY_CODE["senate"].permissions)

    assert "examinations.approve_result" not in examinations
    assert "examinations.approve_result" in senate
    assert "examinations.change_mark" not in senate


def test_management_is_read_only():
    held = ROLES_BY_CODE["management"].permissions
    writes = [
        p
        for p in held
        if any(p.split(".", 1)[1].startswith(verb) for verb in ("add_", "change_", "delete_"))
    ]
    assert not writes, f"management should be read-only but holds {writes}"


def test_applicants_hold_no_permission_beyond_applying_and_browsing_reference_data():
    """Phase 1's invariant was "applicants hold no permissions at all" —
    correct when admissions did not exist yet. Phase 2 gives them exactly what
    self-service application requires (FR-ADM-01): their own application, and
    read access to the programmes/calendar data the form needs. Everything
    else — every other app's data, every write outside admissions — must stay
    off, which is the invariant actually worth protecting now."""
    held = set(ROLES_BY_CODE["applicant"].permissions)

    assert held, "applicants need at least the self-service application permissions"
    other_apps = {p.split(".", 1)[0] for p in held} - {"admissions", "curriculum", "academics"}
    assert not other_apps, f"applicant should not hold permissions in {other_apps}"

    writes = {p for p in held if p.split(".", 1)[1].startswith(("add_", "change_", "delete_"))}
    assert writes.issubset(
        set(ADMISSIONS_SELF)
    ), f"applicant should only write their own admissions records, found {writes - set(ADMISSIONS_SELF)}"


# --------------------------------------------------------- role × endpoint


ENDPOINTS = {
    "students_list": ("get", "/api/v1/registry/students/"),
    "student_create": ("post", "/api/v1/registry/students/"),
    "faculties_list": ("get", "/api/v1/curriculum/faculties/"),
    "faculty_create": ("post", "/api/v1/curriculum/faculties/"),
    "users_list": ("get", "/api/v1/auth/users/"),
    "audit_list": ("get", "/api/v1/audit/entries/"),
    "conflicts_list": ("get", "/api/v1/sync/conflicts/"),
    "calendar": ("get", "/api/v1/academics/calendar/"),
}

# True = must be allowed (not 403), False = must be forbidden.
MATRIX: dict[str, dict[str, bool]] = {
    "student": {
        "students_list": True,  # scoped to their own record
        "student_create": False,
        "faculties_list": True,
        "faculty_create": False,
        "users_list": False,
        "audit_list": False,
        "conflicts_list": False,
        "calendar": True,
    },
    "lecturer": {
        "students_list": True,
        "student_create": False,
        "faculties_list": True,
        "faculty_create": False,
        "users_list": False,
        "audit_list": False,
        "conflicts_list": False,
        "calendar": True,
    },
    "registrar": {
        "students_list": True,
        "student_create": True,
        "faculties_list": True,
        "faculty_create": True,
        "users_list": False,
        "audit_list": False,
        "conflicts_list": True,
        "calendar": True,
    },
    "finance": {
        "students_list": True,
        "student_create": False,
        "faculties_list": False,
        "faculty_create": False,
        "users_list": False,
        "audit_list": False,
        "conflicts_list": False,
        "calendar": True,
    },
    "ict_admin": {
        "students_list": True,
        "student_create": False,
        "faculties_list": True,
        "faculty_create": False,
        "users_list": True,
        "audit_list": True,
        "conflicts_list": True,
        "calendar": True,
    },
    "management": {
        "students_list": True,
        "student_create": False,
        "faculties_list": True,
        "faculty_create": False,
        "users_list": False,
        "audit_list": True,
        "conflicts_list": False,
        "calendar": True,
    },
    "applicant": {
        "students_list": False,
        "student_create": False,
        # Now allowed: browsing programmes is how an applicant fills in the
        # application form (FR-ADM-01) — CURRICULUM_READ, added in Phase 2.
        "faculties_list": True,
        "faculty_create": False,
        "users_list": False,
        "audit_list": False,
        "conflicts_list": False,
        "calendar": True,
    },
}


@pytest.mark.integration
@pytest.mark.parametrize("role_code", sorted(MATRIX))
def test_role_endpoint_matrix(role_code, roles, user_factory, api, institution, semester):
    """Each role against each endpoint.

    Only the authorisation outcome is asserted: 403 means denied, anything else
    means the permission layer let the request through (a 400 from an empty POST
    body is still "allowed").
    """
    user = user_factory(role=role_code, email=f"{role_code}@matrix.test")
    api.force_authenticate(user=user)

    failures = []
    for endpoint, should_allow in MATRIX[role_code].items():
        method, url = ENDPOINTS[endpoint]
        response = getattr(api, method)(url, data={} if method == "post" else None, format="json")
        denied = response.status_code == 403

        if should_allow and denied:
            failures.append(f"{endpoint}: expected access, got 403")
        elif not should_allow and not denied:
            failures.append(f"{endpoint}: expected 403, got {response.status_code}")

    assert not failures, f"{role_code}: " + "; ".join(failures)


@pytest.mark.integration
def test_anonymous_requests_are_rejected(api):
    response = api.get("/api/v1/registry/students/")
    assert response.status_code in {401, 403}


@pytest.mark.integration
def test_an_inactive_account_is_rejected(roles, user_factory, api):
    """Deactivating an account has to take effect immediately, not at token
    expiry — that is how a dismissed member of staff keeps access for a day."""
    user = user_factory(role="registrar", email="dismissed@test.ss", is_active=False)
    api.force_authenticate(user=user)
    assert api.get("/api/v1/registry/students/").status_code == 403
