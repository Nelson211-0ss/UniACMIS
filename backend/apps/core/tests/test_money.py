"""
Money handling.

The rule under test: an amount never travels without its currency, and a
cross-currency amount never travels without the rate that applied. SSP inflation
makes a bare historical decimal uninterpretable.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.core.fields import Currency, Money, validate_money

pytestmark = pytest.mark.django_db


def test_money_normalises_to_decimal():
    assert Money("1500.50").amount == Decimal("1500.50")
    assert Money(1500).amount == Decimal("1500")


def test_currency_is_upper_cased():
    assert Money("100", "ssp").currency == "SSP"


def test_same_currency_arithmetic():
    total = Money("1000", Currency.SSP) + Money("500", Currency.SSP)
    assert total == Money(Decimal("1500"), Currency.SSP)


def test_subtraction_can_go_negative():
    """Refunds and credit notes are real operations; forbidding a negative here
    would push sign handling somewhere less visible."""
    assert (Money("100", "SSP") - Money("150", "SSP")).amount == Decimal("-50")


def test_cross_currency_addition_is_refused():
    """An implicit conversion inside a fee ledger is a reconciliation bug."""
    with pytest.raises(ValueError, match="without an explicit rate"):
        Money("1000", Currency.SSP) + Money("10", Currency.USD)


def test_cross_currency_comparison_is_refused():
    with pytest.raises(ValueError, match="without an explicit rate"):
        _ = Money("1000", Currency.SSP) < Money("10", Currency.USD)


def test_multiplication_keeps_currency():
    assert (Money("250", Currency.USD) * 4) == Money(Decimal("1000"), Currency.USD)


def test_quantized_rounds_half_up():
    # Half-up, not banker's rounding: 10.005 → 10.01, never 10.00.
    assert Money("10.005").quantized().amount == Decimal("10.01")


def test_is_zero():
    assert Money("0").is_zero is True
    assert Money("0.01").is_zero is False


def test_str_includes_the_currency():
    text = str(Money("45000", Currency.SSP))
    assert "SSP" in text
    assert "45,000.00" in text


# ------------------------------------------------------- stored-amount rules


def test_base_currency_needs_no_rate():
    validate_money(currency="SSP", fx_rate=None, fx_rate_date=None)  # must not raise


def test_a_foreign_amount_without_a_rate_is_refused():
    """SSP inflation makes a historical USD figure uninterpretable without the
    rate that applied — so it cannot be stored without one."""
    with pytest.raises(ValidationError) as raised:
        validate_money(currency="USD", fx_rate=None, fx_rate_date=None)
    assert "fx_rate" in raised.value.message_dict


def test_a_foreign_amount_with_a_rate_and_date_is_accepted():
    validate_money(
        currency="USD",
        fx_rate=Decimal("5200.000000"),
        fx_rate_date=date(2026, 8, 17),
    )


def test_a_rate_without_its_date_is_refused():
    """A rate with no date cannot be checked against anything later."""
    with pytest.raises(ValidationError) as raised:
        validate_money(currency="USD", fx_rate=Decimal("5200"), fx_rate_date=None)
    assert "fx_rate_date" in raised.value.message_dict


@pytest.mark.parametrize("rate", ["0", "-1"])
def test_a_non_positive_rate_is_refused(rate):
    with pytest.raises(ValidationError) as raised:
        validate_money(currency="USD", fx_rate=Decimal(rate), fx_rate_date=date(2026, 8, 17))
    assert "fx_rate" in raised.value.message_dict


def test_the_base_currency_can_be_overridden():
    """An institution whose base currency is USD must not be asked for a USD rate."""
    validate_money(currency="USD", fx_rate=None, fx_rate_date=None, base_currency="USD")
    with pytest.raises(ValidationError):
        validate_money(currency="SSP", fx_rate=None, fx_rate_date=None, base_currency="USD")
