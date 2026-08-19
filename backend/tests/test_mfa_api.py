"""MFA API: enrolment, and its enforcement at login (NFR-SEC-04)."""

from __future__ import annotations

import pyotp
import pytest

from apps.accounts.models import MFABackupCode
from tests.constants import PASSWORD

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/login/"
MFA_SETUP = "/api/v1/auth/mfa/setup/"
MFA_CONFIRM = "/api/v1/auth/mfa/confirm/"
MFA_DISABLE = "/api/v1/auth/mfa/disable/"


@pytest.mark.integration
def test_enrolling_end_to_end(roles, user_factory, as_user):
    user = user_factory(role="registrar", email="mfa-setup@test.ss")
    client = as_user(user)

    setup = client.post(MFA_SETUP)
    assert setup.status_code == 200
    user.refresh_from_db()
    secret = user.mfa_secret
    assert secret and secret in setup.data["provisioning_uri"]

    confirm = client.post(MFA_CONFIRM, {"code": pyotp.TOTP(secret).now()}, format="json")
    assert confirm.status_code == 200
    assert len(confirm.data["backup_codes"]) == 10
    user.refresh_from_db()
    assert user.mfa_enabled is True


@pytest.mark.integration
def test_confirming_with_a_wrong_code_is_rejected(roles, user_factory, as_user):
    user = user_factory(role="registrar", email="mfa-wrong@test.ss")
    client = as_user(user)
    client.post(MFA_SETUP)
    response = client.post(MFA_CONFIRM, {"code": "000000"}, format="json")
    assert response.status_code == 400


@pytest.mark.integration
def test_login_with_mfa_enabled_requires_a_code(roles, user_factory, api):
    user = user_factory(role="registrar", email="mfa-login@test.ss")
    import apps.accounts.services as services

    services.start_mfa_enrolment(user)
    services.confirm_mfa_enrolment(user, code=pyotp.TOTP(user.mfa_secret).now())

    without_code = api.post(LOGIN, {"email": user.email, "password": PASSWORD}, format="json")
    assert without_code.status_code == 400

    with_wrong_code = api.post(
        LOGIN, {"email": user.email, "password": PASSWORD, "otp": "000000"}, format="json"
    )
    assert with_wrong_code.status_code == 400

    with_right_code = api.post(
        LOGIN,
        {"email": user.email, "password": PASSWORD, "otp": pyotp.TOTP(user.mfa_secret).now()},
        format="json",
    )
    assert with_right_code.status_code == 200
    assert "access" in with_right_code.data


@pytest.mark.integration
def test_login_with_mfa_enabled_accepts_a_backup_code(roles, user_factory, api):
    import apps.accounts.services as services

    user = user_factory(role="registrar", email="mfa-backup@test.ss")
    services.start_mfa_enrolment(user)
    codes = services.confirm_mfa_enrolment(user, code=pyotp.TOTP(user.mfa_secret).now())

    response = api.post(
        LOGIN, {"email": user.email, "password": PASSWORD, "otp": codes[0]}, format="json"
    )
    assert response.status_code == 200

    reused = api.post(
        LOGIN, {"email": user.email, "password": PASSWORD, "otp": codes[0]}, format="json"
    )
    assert reused.status_code == 400


@pytest.mark.integration
def test_disabling_mfa_requires_the_current_password(roles, user_factory, as_user):
    import apps.accounts.services as services

    user = user_factory(role="registrar", email="mfa-disable@test.ss")
    services.start_mfa_enrolment(user)
    services.confirm_mfa_enrolment(user, code=pyotp.TOTP(user.mfa_secret).now())
    client = as_user(user)

    wrong = client.post(MFA_DISABLE, {"current_password": "not-it"}, format="json")
    assert wrong.status_code == 400

    right = client.post(MFA_DISABLE, {"current_password": PASSWORD}, format="json")
    assert right.status_code == 200
    user.refresh_from_db()
    assert user.mfa_enabled is False
    assert MFABackupCode.objects.filter(user=user).count() == 0
