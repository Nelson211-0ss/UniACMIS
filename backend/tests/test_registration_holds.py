"""
Registration holds (FR-ENR-03) — the cross-module integration test.

Through Phase 3, the point of this file was the *absence* of the finance
module: unpaid fees blocking registration is a rule that spans two modules,
and it was tested through the hold-provider port with a demo stand-in years
before `finance` existed, so that Phase 4 could replace the implementation
without these tests changing at all.

Phase 4 has now landed exactly that way — `apps.finance.providers.FeeBalanceHoldProvider`
is registered for real (see `apps/finance/tests/test_services.py` for the
integration test against a genuine invoice) — and the demo provider stays
registered in this settings profile too (`ENABLE_DEMO_HOLD_PROVIDER=True` in
`config.settings.test`), deliberately: these tests exercise the generic
aggregation mechanism itself (several providers accumulating, one that fails
blocking rather than being ignored, a non-blocking advisory hold, duplicate
registration not double-counting) without needing a real invoice for every
case, which is what makes the demo seam still worth keeping.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.core.exceptions import BlockedByHold
from apps.core.ports import Hold, HoldProvider
from apps.core.providers.holds import (
    DemoFeeBalanceHoldProvider,
    clear_demo_balances,
    set_demo_balance,
)
from apps.core.services import holds as hold_services
from apps.core.services.registry import registry
from apps.registry.services import assert_can_register, registration_holds

pytestmark = pytest.mark.django_db


def test_a_student_with_no_balance_is_clear(student):
    clear_demo_balances()
    set_demo_balance(student.pk, 0)
    assert registration_holds(student.pk) == []
    assert hold_services.is_clear(student.pk) is True


@pytest.mark.integration
def test_an_unpaid_balance_blocks_registration(student):
    """The Phase 4 rule, working in Phase 1 through the port."""
    set_demo_balance(student.pk, Decimal("45000.00"))

    holds = registration_holds(student.pk)
    assert len(holds) == 1
    assert holds[0]["code"] == "unpaid_fees"
    assert "45,000.00" in holds[0]["message"]
    assert holds[0]["blocking"] is True

    with pytest.raises(BlockedByHold) as raised:
        assert_can_register(student.pk)

    assert raised.value.status_code == 409
    assert raised.value.details["holds"][0]["code"] == "unpaid_fees"


@pytest.mark.integration
def test_clearing_the_balance_lifts_the_hold(student):
    set_demo_balance(student.pk, Decimal("45000.00"))
    with pytest.raises(BlockedByHold):
        assert_can_register(student.pk)

    set_demo_balance(student.pk, Decimal("0.00"))
    assert_can_register(student.pk)  # must not raise


@pytest.mark.integration
def test_holds_from_several_modules_accumulate(student):
    """Registration, results and graduation clearance all ask the same question,
    and more than one module can answer no."""

    class MissingDocumentsProvider:
        source = "registry"

        def holds_for(self, student_id: int) -> list[Hold]:
            return [
                Hold(
                    code="missing_documents",
                    message="Certified copy of the secondary certificate is missing.",
                    source=self.source,
                )
            ]

    provider = MissingDocumentsProvider()
    registry.register(HoldProvider, provider)
    set_demo_balance(student.pk, Decimal("1000.00"))

    try:
        codes = {hold["code"] for hold in registration_holds(student.pk)}
        assert codes == {"unpaid_fees", "missing_documents"}
    finally:
        registry.unregister(HoldProvider, MissingDocumentsProvider)


@pytest.mark.integration
def test_a_failing_provider_blocks_rather_than_being_ignored(student):
    """If finance is unreachable we do not know that fees are paid. Letting the
    student through is the more expensive mistake, so an error is itself a hold.
    """

    class BrokenProvider:
        source = "finance"

        def holds_for(self, student_id: int) -> list[Hold]:
            raise ConnectionError("finance service unreachable")

    registry.register(HoldProvider, BrokenProvider())

    try:
        holds = registration_holds(student.pk)
        assert any(h["code"] == "hold_check_failed" for h in holds)
        with pytest.raises(BlockedByHold):
            assert_can_register(student.pk)
    finally:
        registry.unregister(HoldProvider, BrokenProvider)


@pytest.mark.integration
def test_a_non_blocking_hold_is_reported_but_does_not_block(student):
    """A warning a registrar should see without it stopping the registration."""

    class AdvisoryProvider:
        source = "library"

        def holds_for(self, student_id: int) -> list[Hold]:
            return [
                Hold(
                    code="overdue_book",
                    message="One overdue library item.",
                    source=self.source,
                    blocking=False,
                )
            ]

    registry.register(HoldProvider, AdvisoryProvider())
    clear_demo_balances()
    set_demo_balance(student.pk, 0)

    try:
        holds = registration_holds(student.pk)
        assert any(h["code"] == "overdue_book" for h in holds)
        assert_can_register(student.pk)  # must not raise
    finally:
        registry.unregister(HoldProvider, AdvisoryProvider)


@pytest.mark.integration
def test_the_holds_endpoint_reports_the_same_answer(student, registrar, as_user):
    set_demo_balance(student.pk, Decimal("45000.00"))

    response = as_user(registrar).get(f"/api/v1/registry/students/{student.pk}/holds/")

    assert response.status_code == 200
    assert response.data["clear"] is False
    assert response.data["holds"][0]["code"] == "unpaid_fees"


@pytest.mark.integration
def test_the_holds_endpoint_reports_a_clear_student(student, registrar, as_user):
    clear_demo_balances()
    set_demo_balance(student.pk, 0)

    response = as_user(registrar).get(f"/api/v1/registry/students/{student.pk}/holds/")

    assert response.status_code == 200
    assert response.data["clear"] is True
    assert response.data["holds"] == []


def test_registering_a_provider_twice_does_not_double_count(student):
    """AppConfig.ready() can run more than once; a duplicated provider would
    report the same hold twice."""
    set_demo_balance(student.pk, Decimal("500.00"))

    registry.register(HoldProvider, DemoFeeBalanceHoldProvider())
    registry.register(HoldProvider, DemoFeeBalanceHoldProvider())

    assert len(registration_holds(student.pk)) == 1
