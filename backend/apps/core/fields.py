"""
Money handling.

Rule for the whole system: **an amount is never stored without its currency.**
Fees are quoted in SSP and in USD (SRS §2.5), and SSP inflation means a
historical figure is not interpretable without the rate that applied when it was
recorded. Anything holding a cross-currency amount therefore also records the FX
rate and the date it was captured.

Phase 1 defines these types; `finance` uses them from Phase 4. Defining them now
is deliberate — retrofitting currency onto a live fee ledger has no clean
migration.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

MONEY_MAX_DIGITS = 16
MONEY_DECIMAL_PLACES = 2
FX_MAX_DIGITS = 18
FX_DECIMAL_PLACES = 6

TWO_PLACES = Decimal("0.01")


class Currency(models.TextChoices):
    SSP = "SSP", _("South Sudanese Pound")
    USD = "USD", _("US Dollar")
    KES = "KES", _("Kenyan Shilling")
    UGX = "UGX", _("Ugandan Shilling")
    EUR = "EUR", _("Euro")
    GBP = "GBP", _("Pound Sterling")


@dataclass(frozen=True)
class Money:
    """An amount together with its currency.

    Arithmetic across currencies raises rather than guessing a rate — an
    implicit conversion in a fee ledger is a reconciliation bug waiting to
    happen.
    """

    amount: Decimal
    currency: str = Currency.SSP

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            object.__setattr__(self, "amount", Decimal(str(self.amount)))
        object.__setattr__(self, "currency", str(self.currency).upper())

    def _assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"Refusing to combine {self.currency} with {other.currency} without an explicit rate."
            )

    def __add__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: int | Decimal) -> Money:
        return Money(self.amount * Decimal(str(factor)), self.currency)

    def __lt__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount < other.amount

    def quantized(self) -> Money:
        return Money(self.amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP), self.currency)

    @property
    def is_zero(self) -> bool:
        return self.amount == 0

    def __str__(self) -> str:
        return f"{self.currency} {self.amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP):,}"


class MoneyAmountField(models.DecimalField):
    """Decimal sized for SSP figures, which run large.

    Negative values are permitted: refunds, credit notes and reversals are real
    finance operations, and forbidding them here would push those modules into
    storing sign information somewhere else.
    """

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("max_digits", MONEY_MAX_DIGITS)
        kwargs.setdefault("decimal_places", MONEY_DECIMAL_PLACES)
        super().__init__(*args, **kwargs)


class CurrencyField(models.CharField):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("max_length", 3)
        kwargs.setdefault("choices", Currency.choices)
        kwargs.setdefault("default", Currency.SSP)
        super().__init__(*args, **kwargs)


def validate_money(
    *,
    currency: str,
    fx_rate: Decimal | None,
    fx_rate_date: object | None,
    base_currency: str | None = None,
) -> None:
    """The rule every stored amount must satisfy.

    A pure function rather than only a model hook, so it is testable before any
    model uses it and reusable by serializers and import tooling that never
    instantiate a model at all.

    Raises `ValidationError` keyed by field name.
    """
    base = base_currency or getattr(settings, "DEFAULT_CURRENCY", Currency.SSP)

    if currency != base and fx_rate is None:
        raise ValidationError(
            {
                "fx_rate": _(
                    "An amount in %(currency)s needs the exchange rate that applied, "
                    "otherwise it cannot be reconciled later."
                )
                % {"currency": currency},
            }
        )

    if fx_rate is not None and fx_rate <= 0:
        raise ValidationError({"fx_rate": _("Exchange rate must be greater than zero.")})

    if fx_rate is not None and fx_rate_date is None:
        raise ValidationError({"fx_rate_date": _("Record the date the exchange rate was taken.")})


class MoneyMixin(models.Model):
    """Abstract holder for a single monetary value with its currency and rate."""

    amount = MoneyAmountField(_("amount"))
    currency = CurrencyField(_("currency"))
    fx_rate = models.DecimalField(
        _("exchange rate to base currency"),
        max_digits=FX_MAX_DIGITS,
        decimal_places=FX_DECIMAL_PLACES,
        null=True,
        blank=True,
        help_text=_("Units of the institution's base currency per unit of this currency."),
    )
    fx_rate_date = models.DateField(_("exchange rate date"), null=True, blank=True)

    class Meta:
        abstract = True

    @property
    def money(self) -> Money:
        return Money(self.amount, self.currency)

    @property
    def base_amount(self) -> Decimal | None:
        """Value in the institution's base currency, or None if unconvertible."""
        base = getattr(settings, "DEFAULT_CURRENCY", Currency.SSP)
        if self.currency == base:
            return self.amount
        if self.fx_rate is None:
            return None
        return (self.amount * self.fx_rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    def clean(self) -> None:
        super().clean()
        validate_money(
            currency=self.currency,
            fx_rate=self.fx_rate,
            fx_rate_date=self.fx_rate_date,
        )
