"""
The real fee-balance hold provider (FR-ENR-03), replacing the Phase 1 demo
stub in `apps.core.providers.holds` — which stays in place rather than being
deleted, since a handful of Phase 2/3 tests still use its `set_demo_balance`
seam to exercise the generic "a hold blocks registration" behaviour without
depending on a real invoice existing. The provider registry de-duplicates
only by class, so both can be registered at once without double-counting a
single real hold: the demo provider only ever fires for a balance someone
explicitly set with `set_demo_balance`, which no real student has.
"""

from __future__ import annotations

from apps.academics.services import config as academics_config
from apps.core.ports import Hold, HoldProvider
from apps.core.services.registry import registry
from apps.finance import services


class FeeBalanceHoldProvider:
    source = "finance"

    def holds_for(self, student_id: int) -> list[Hold]:
        balance = services.fee_balance_for_student(student_id)
        if balance <= 0:
            return []
        currency = academics_config.base_currency()
        return [
            Hold(
                code="unpaid_fees",
                message=f"Outstanding fee balance: {currency} {balance:,.2f}",
                source=self.source,
                blocking=True,
                details={"balance": str(balance), "currency": currency},
            )
        ]


def register() -> None:
    registry.register(HoldProvider, FeeBalanceHoldProvider())
