"""
Stub hold provider.

FR-ENR-03 (unpaid fees block registration) is a cross-module rule, and the module
that will answer it — `finance` — does not exist until Phase 4. Rather than defer
the rule and the test with it, Phase 1 ships a stub that answers the same question
through the same port. The integration test proves the wiring today; Phase 4
swaps the implementation and the test keeps passing.

Off unless `ENABLE_DEMO_HOLD_PROVIDER` is set, and production refuses to boot with
it enabled.
"""

from __future__ import annotations

from decimal import Decimal

from apps.core.ports import Hold, HoldProvider
from apps.core.services.registry import registry

# Explicit per-student balances, used by tests.
_DEMO_BALANCES: dict[int, Decimal] = {}

# Students whose id is divisible by this are treated as owing fees, so seeded
# demo data exercises the blocked path without any extra setup.
DEMO_DEFAULTER_MODULUS = 5
DEMO_DEFAULT_BALANCE = Decimal("45000.00")


class DemoFeeBalanceHoldProvider:
    """Stands in for `finance.FeeBalanceHoldProvider` until Phase 4."""

    source = "finance (stub)"

    def holds_for(self, student_id: int) -> list[Hold]:
        balance = _DEMO_BALANCES.get(student_id)
        if balance is None and student_id % DEMO_DEFAULTER_MODULUS == 0:
            balance = DEMO_DEFAULT_BALANCE

        if not balance or balance <= 0:
            return []

        return [
            Hold(
                code="unpaid_fees",
                message=f"Outstanding fee balance: SSP {balance:,.2f}",
                source=self.source,
                blocking=True,
                details={"balance": str(balance), "currency": "SSP"},
            )
        ]


def register_demo_provider() -> None:
    registry.register(HoldProvider, DemoFeeBalanceHoldProvider())


# --------------------------------------------------------------- test helpers


def set_demo_balance(student_id: int, amount: Decimal | str | int) -> None:
    _DEMO_BALANCES[student_id] = Decimal(str(amount))


def clear_demo_balances() -> None:
    _DEMO_BALANCES.clear()
