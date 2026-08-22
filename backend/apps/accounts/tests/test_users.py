"""User & role administration via the API (accounts.UserViewSet)."""

from __future__ import annotations

import pytest

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_creating_a_user_sets_a_usable_password(as_user, ict_admin):
    api = as_user(ict_admin)
    response = api.post(
        "/api/v1/auth/users/",
        {
            "email": "new.lecturer@test.ss",
            "first_name": "New",
            "last_name": "Lecturer",
            "password": "TempPass123",
        },
        format="json",
    )
    assert response.status_code == 201, response.data

    created = User.objects.get(email="new.lecturer@test.ss")
    assert created.check_password("TempPass123")
    assert created.must_change_password is True
    # The password is never echoed back.
    assert "password" not in response.data


def test_creating_a_user_without_a_password_is_rejected(as_user, ict_admin):
    api = as_user(ict_admin)
    response = api.post(
        "/api/v1/auth/users/",
        {"email": "no.password@test.ss", "first_name": "No", "last_name": "Password"},
        format="json",
    )
    assert response.status_code == 400
    assert "password" in response.data["error"]["details"]


def test_updating_a_user_without_a_password_leaves_it_unchanged(as_user, ict_admin, user_factory):
    target = user_factory(email="unchanged@test.ss")
    original_hash = target.password

    api = as_user(ict_admin)
    response = api.patch(
        f"/api/v1/auth/users/{target.pk}/", {"phone": "+211900000000"}, format="json"
    )
    assert response.status_code == 200

    target.refresh_from_db()
    assert target.password == original_hash
    assert target.phone == "+211900000000"


def test_a_supplied_password_on_update_is_rehashed_not_stored_raw(as_user, ict_admin, user_factory):
    target = user_factory(email="reset-me@test.ss")

    api = as_user(ict_admin)
    response = api.patch(
        f"/api/v1/auth/users/{target.pk}/", {"password": "BrandNewPass1"}, format="json"
    )
    assert response.status_code == 200

    target.refresh_from_db()
    assert target.check_password("BrandNewPass1")
    assert target.password != "BrandNewPass1"


def test_only_ict_admin_may_create_a_user(as_user, registrar):
    api = as_user(registrar)
    response = api.post(
        "/api/v1/auth/users/",
        {
            "email": "blocked@test.ss",
            "first_name": "No",
            "last_name": "Access",
            "password": "TempPass123",
        },
        format="json",
    )
    assert response.status_code == 403


def test_granting_and_revoking_a_role_via_the_api(as_user, ict_admin, user_factory):
    target = user_factory(email="grant-target@test.ss")
    api = as_user(ict_admin)

    grant = api.post(
        f"/api/v1/auth/users/{target.pk}/grant-role/",
        {"role_code": "lecturer", "reason": "New teaching assignment"},
        format="json",
    )
    assert grant.status_code == 200
    assert target.role_codes() == ["lecturer"]

    revoke = api.post(
        f"/api/v1/auth/users/{target.pk}/revoke-role/",
        {"role_code": "lecturer", "reason": "Role no longer needed"},
        format="json",
    )
    assert revoke.status_code == 204
    assert target.role_codes() == []
