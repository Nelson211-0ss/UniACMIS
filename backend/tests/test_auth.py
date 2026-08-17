"""
Authentication: JWT issue and refresh, lockout, and the audit record of sign-ins
(NFR-SEC-03, NFR-SEC-04).
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from apps.audit.models import AuditAction, AuditLog
from tests.constants import PASSWORD

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/login/"
REFRESH = "/api/v1/auth/refresh/"
ME = "/api/v1/auth/me/"
LOGOUT = "/api/v1/auth/logout/"


@pytest.mark.integration
def test_valid_credentials_return_a_token_pair(roles, user_factory, api):
    user = user_factory(role="registrar", email="login@test.ss")

    response = api.post(LOGIN, {"email": user.email, "password": PASSWORD}, format="json")

    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" in response.data
    assert response.data["user"]["roles"] == ["registrar"]


@pytest.mark.integration
def test_the_email_is_case_insensitive(roles, user_factory, api):
    user_factory(role="registrar", email="mixed@test.ss")
    response = api.post(LOGIN, {"email": "MIXED@TEST.SS", "password": PASSWORD}, format="json")
    assert response.status_code == 200


@pytest.mark.integration
def test_a_wrong_password_is_rejected(roles, user_factory, api):
    user = user_factory(email="wrong@test.ss")
    response = api.post(LOGIN, {"email": user.email, "password": "not-the-password"}, format="json")
    assert response.status_code == 401


@pytest.mark.integration
def test_a_successful_sign_in_is_audited(roles, user_factory, api):
    user = user_factory(role="registrar", email="audited@test.ss")
    api.post(LOGIN, {"email": user.email, "password": PASSWORD}, format="json")

    entry = AuditLog.objects.filter(action=AuditAction.LOGIN).first()
    assert entry is not None
    assert entry.actor_id == user.pk
    assert "registrar" in entry.description


@pytest.mark.integration
def test_a_failed_sign_in_is_audited(roles, user_factory, api):
    user = user_factory(email="failer@test.ss")
    api.post(LOGIN, {"email": user.email, "password": "nope"}, format="json")

    entry = AuditLog.objects.filter(action=AuditAction.LOGIN_FAILED).first()
    assert entry is not None
    assert entry.actor_id == user.pk


@pytest.mark.integration
def test_a_failed_sign_in_for_an_unknown_address_is_still_audited(db, api):
    """A run of attempts against addresses that do not exist is itself the signal
    worth keeping."""
    api.post(LOGIN, {"email": "nobody@test.ss", "password": "guess"}, format="json")

    entry = AuditLog.objects.filter(action=AuditAction.LOGIN_FAILED).first()
    assert entry is not None
    assert entry.actor_id is None
    assert "nobody@test.ss" in entry.description


@pytest.mark.integration
def test_failed_attempts_accumulate(roles, user_factory, api):
    user = user_factory(email="counter@test.ss")

    for _ in range(3):
        api.post(LOGIN, {"email": user.email, "password": "nope"}, format="json")

    user.refresh_from_db()
    assert user.failed_login_attempts == 3
    assert not user.is_locked_out


@pytest.mark.integration
@override_settings(LOGIN_MAX_FAILED_ATTEMPTS=3, LOGIN_LOCKOUT_MINUTES=15)
def test_the_account_locks_after_the_configured_attempts(roles, user_factory, api):
    """Campus machines are shared and passwords get written on desks."""
    user = user_factory(email="locked@test.ss")

    for _ in range(3):
        api.post(LOGIN, {"email": user.email, "password": "nope"}, format="json")

    user.refresh_from_db()
    assert user.is_locked_out

    # Even the correct password is refused while the lock holds.
    response = api.post(LOGIN, {"email": user.email, "password": PASSWORD}, format="json")
    assert response.status_code == 400
    assert "locked" in str(response.data).lower()


@pytest.mark.integration
def test_a_successful_sign_in_clears_the_failure_count(roles, user_factory, api):
    user = user_factory(role="registrar", email="recovered@test.ss")
    api.post(LOGIN, {"email": user.email, "password": "nope"}, format="json")

    api.post(LOGIN, {"email": user.email, "password": PASSWORD}, format="json")

    user.refresh_from_db()
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


@pytest.mark.integration
def test_the_sign_in_ip_is_recorded(roles, user_factory, api):
    user = user_factory(role="registrar", email="ip@test.ss")
    api.post(
        LOGIN,
        {"email": user.email, "password": PASSWORD},
        format="json",
        REMOTE_ADDR="10.11.12.13",
    )

    user.refresh_from_db()
    assert user.last_login_ip == "10.11.12.13"
    assert user.last_login is not None


@pytest.mark.integration
def test_an_inactive_account_cannot_sign_in(roles, user_factory, api):
    user = user_factory(email="inactive@test.ss", is_active=False)
    response = api.post(LOGIN, {"email": user.email, "password": PASSWORD}, format="json")
    assert response.status_code == 401


@pytest.mark.integration
def test_the_token_carries_roles_and_the_password_flag(roles, user_factory, api):
    """The PWA renders its navigation from these without an extra round trip on a
    slow link."""
    import jwt

    user = user_factory(role="lecturer", email="claims@test.ss")
    user.must_change_password = True
    user.save(update_fields=["must_change_password"])

    response = api.post(LOGIN, {"email": user.email, "password": PASSWORD}, format="json")
    claims = jwt.decode(response.data["access"], options={"verify_signature": False})

    assert claims["roles"] == ["lecturer"]
    assert claims["must_change_password"] is True
    assert claims["name"] == user.get_full_name()


@pytest.mark.integration
def test_refresh_issues_a_new_access_token(roles, user_factory, api):
    user = user_factory(role="registrar", email="refresh@test.ss")
    tokens = api.post(LOGIN, {"email": user.email, "password": PASSWORD}, format="json").data

    response = api.post(REFRESH, {"refresh": tokens["refresh"]}, format="json")

    assert response.status_code == 200
    assert "access" in response.data


@pytest.mark.integration
def test_a_rotated_refresh_token_stops_working(roles, user_factory, api):
    """Rotation with blacklisting: a refresh token copied from a shared machine
    dies as soon as the real user refreshes."""
    user = user_factory(role="registrar", email="rotate@test.ss")
    tokens = api.post(LOGIN, {"email": user.email, "password": PASSWORD}, format="json").data

    first = api.post(REFRESH, {"refresh": tokens["refresh"]}, format="json")
    assert first.status_code == 200

    reused = api.post(REFRESH, {"refresh": tokens["refresh"]}, format="json")
    assert reused.status_code == 401


@pytest.mark.integration
def test_me_returns_identity_roles_and_permissions(roles, user_factory, as_user):
    user = user_factory(role="registrar", email="me@test.ss")
    response = as_user(user).get(ME)

    assert response.status_code == 200
    assert response.data["email"] == user.email
    assert response.data["roles"] == ["registrar"]
    assert "registry.add_student" in response.data["permissions"]


@pytest.mark.integration
def test_me_requires_authentication(api):
    assert api.get(ME).status_code in {401, 403}


@pytest.mark.integration
def test_signing_out_is_audited(roles, user_factory, api):
    user = user_factory(role="registrar", email="out@test.ss")
    tokens = api.post(LOGIN, {"email": user.email, "password": PASSWORD}, format="json").data

    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    response = api.post(LOGOUT, {"refresh": tokens["refresh"]}, format="json")

    assert response.status_code == 205
    assert AuditLog.objects.filter(action=AuditAction.LOGOUT, actor=user).exists()


@pytest.mark.integration
def test_signing_out_blacklists_the_refresh_token(roles, user_factory, api):
    user = user_factory(role="registrar", email="blacklist@test.ss")
    tokens = api.post(LOGIN, {"email": user.email, "password": PASSWORD}, format="json").data

    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    api.post(LOGOUT, {"refresh": tokens["refresh"]}, format="json")
    api.credentials()

    assert api.post(REFRESH, {"refresh": tokens["refresh"]}, format="json").status_code == 401


@pytest.mark.integration
def test_changing_a_password_clears_the_forced_change_flag(roles, user_factory, as_user):
    user = user_factory(role="registrar", email="change@test.ss")
    user.must_change_password = True
    user.save(update_fields=["must_change_password"])

    response = as_user(user).post(
        "/api/v1/auth/change-password/",
        {"current_password": PASSWORD, "new_password": "a-much-longer-new-secret-42"},
        format="json",
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.must_change_password is False
    assert user.check_password("a-much-longer-new-secret-42")


@pytest.mark.integration
def test_a_weak_new_password_is_refused(roles, user_factory, as_user):
    user = user_factory(role="registrar", email="weak@test.ss")
    response = as_user(user).post(
        "/api/v1/auth/change-password/",
        {"current_password": PASSWORD, "new_password": "short"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.integration
def test_the_wrong_current_password_is_refused(roles, user_factory, as_user):
    user = user_factory(role="registrar", email="wrongcurrent@test.ss")
    response = as_user(user).post(
        "/api/v1/auth/change-password/",
        {"current_password": "not-it", "new_password": "a-much-longer-new-secret-42"},
        format="json",
    )
    assert response.status_code == 400


# ---------------------------------------------------------------- error shape


@pytest.mark.integration
def test_errors_use_the_documented_envelope(roles, user_factory, as_user):
    """One shape for every error, carrying a request id that also appears on audit
    rows — so a user's screenshot is enough to find the server-side trail."""
    user = user_factory(role="registrar", email="envelope@test.ss")
    response = as_user(user).get("/api/v1/registry/students/999999/")

    assert response.status_code == 404
    assert set(response.data["error"]) == {"code", "message", "details", "request_id"}
    assert response.data["error"]["code"] == "not_found"
    assert response.data["error"]["request_id"]


@pytest.mark.integration
def test_the_request_id_is_returned_in_a_header(roles, user_factory, as_user):
    user = user_factory(role="registrar", email="header@test.ss")
    response = as_user(user).get(ME)
    assert response.headers.get("X-Request-ID")


@pytest.mark.integration
def test_an_inbound_request_id_is_honoured(roles, user_factory, as_user):
    """A write queued offline carries its id from the device, so the trail links
    the eventual server-side record back to what the user saw at the time."""
    user = user_factory(role="registrar", email="inbound@test.ss")
    response = as_user(user).get(ME, HTTP_X_REQUEST_ID="device-generated-1234")
    assert response.headers["X-Request-ID"] == "device-generated-1234"


@pytest.mark.integration
def test_health_check_needs_no_authentication(api):
    response = api.get("/healthz/")
    assert response.status_code == 200
    assert response.data["checks"]["database"] == "ok"
