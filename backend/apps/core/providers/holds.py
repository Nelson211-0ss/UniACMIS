"""
Stub hold provider.

FR-ENR-03 (unpaid fees block registration) is a cross-module rule, and the module
that will answer it — `finance` — does not exist until Phase 4. Rather than defer
the rule and the test with it, Phase 1 ships a stub that answers the same question
through the same port. The integration test proves the wiring today; Phase 4
swaps the implementation and the test keeps passing.

Off unless `ENABLE_DEMO_HOLD_PROVIDER` is set, and production refuses to boot with
it enabled.

Deliberately consults only `_DEMO_BALANCES` — nothing here infers a balance from
a student's id. An earlier version flagged "every 5th student id" as a defaulter
so seeded demo data looked realistic without extra setup, but that made the
provider *nondeterministic from a test's point of view*: Postgres sequence
values are not rolled back with a test's transaction, so which student ids are
multiples of 5 drifts with how many rows earlier tests happened to create, and a
test that never called `set_demo_balance` could still trip over a hold it never
asked for. Realistic-looking demo data is `seed_demo`'s job, not this provider's.
"""

from __future__ import annotations

from decimal import Decimal

from apps.core.ports import Hold, HoldProvider
from apps.core.services.registry import registry

# Explicit per-student balances, set by tests and by seed_demo.
_DEMO_BALANCES: dict[int, Decimal] = {}

DEMO_DEFAULT_BALANCE = Decimal("45000.00")


class DemoFeeBalanceHoldProvider:
    """Stands in for `finance.FeeBalanceHoldProvider` until Phase 4."""

    source = "finance (stub)"

    def holds_for(self, student_id: int) -> list[Hold]:
        balance = _DEMO_BALANCES.get(student_id)

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
