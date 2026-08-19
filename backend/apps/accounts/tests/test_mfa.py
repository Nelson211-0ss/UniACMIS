"""MFA enrolment and verification (NFR-SEC-04)."""

from __future__ import annotations

import pyotp
import pytest

from apps.accounts import services
from apps.accounts.models import MFABackupCode

pytestmark = pytest.mark.django_db


def test_starting_enrolment_generates_a_secret_and_uri(user_factory):
    user = user_factory()
    uri = services.start_mfa_enrolment(user)
    user.refresh_from_db()
    assert user.mfa_secret
    assert user.mfa_enabled is False
    assert user.mfa_secret in uri
    assert "UniACMIS" in uri


def test_cannot_start_enrolment_twice_while_already_enabled(user_factory):
    user = user_factory()
    services.start_mfa_enrolment(user)
    services.confirm_mfa_enrolment(user, code=pyotp.TOTP(user.mfa_secret).now())
    with pytest.raises(services.MFAAlreadyEnabled):
        services.start_mfa_enrolment(user)


def test_confirming_before_starting_is_rejected(user_factory):
    user = user_factory()
    with pytest.raises(services.MFANotStarted):
        services.confirm_mfa_enrolment(user, code="123456")


def test_confirming_with_a_wrong_code_is_rejected(user_factory):
    user = user_factory()
    services.start_mfa_enrolment(user)
    with pytest.raises(services.InvalidMFACode):
        services.confirm_mfa_enrolment(user, code="000000")
    user.refresh_from_db()
    assert user.mfa_enabled is False


def test_confirming_with_the_right_code_enables_mfa_and_issues_backup_codes(user_factory):
    user = user_factory()
    services.start_mfa_enrolment(user)
    codes = services.confirm_mfa_enrolment(user, code=pyotp.TOTP(user.mfa_secret).now())
    user.refresh_from_db()
    assert user.mfa_enabled is True
    assert len(codes) == services.BACKUP_CODE_COUNT
    assert MFABackupCode.objects.filter(user=user).count() == services.BACKUP_CODE_COUNT


def test_verify_mfa_code_accepts_a_valid_totp(user_factory):
    user = user_factory()
    services.start_mfa_enrolment(user)
    services.confirm_mfa_enrolment(user, code=pyotp.TOTP(user.mfa_secret).now())
    assert services.verify_mfa_code(user, pyotp.TOTP(user.mfa_secret).now()) is True


def test_verify_mfa_code_rejects_a_wrong_code(user_factory):
    user = user_factory()
    services.start_mfa_enrolment(user)
    services.confirm_mfa_enrolment(user, code=pyotp.TOTP(user.mfa_secret).now())
    assert services.verify_mfa_code(user, "000000") is False


def test_a_backup_code_works_once_and_only_once(user_factory):
    user = user_factory()
    services.start_mfa_enrolment(user)
    codes = services.confirm_mfa_enrolment(user, code=pyotp.TOTP(user.mfa_secret).now())

    assert services.verify_mfa_code(user, codes[0]) is True
    assert services.verify_mfa_code(user, codes[0]) is False


def test_disabling_mfa_clears_the_secret_and_backup_codes(user_factory):
    user = user_factory()
    services.start_mfa_enrolment(user)
    services.confirm_mfa_enrolment(user, code=pyotp.TOTP(user.mfa_secret).now())

    services.disable_mfa(user)
    user.refresh_from_db()
    assert user.mfa_enabled is False
    assert user.mfa_secret == ""
    assert MFABackupCode.objects.filter(user=user).count() == 0


def test_verify_mfa_code_with_no_secret_and_no_backup_codes_is_false(user_factory):
    user = user_factory()
    assert services.verify_mfa_code(user, "123456") is False
    assert services.verify_mfa_code(user, "") is False
