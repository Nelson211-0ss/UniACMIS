"""
Gapless, race-free identifier allocation.

The concurrency test is the point of the module: two registry clerks admitting
students at the same moment must not be able to mint the same number, and this
number ends up printed on a certificate.
"""

from __future__ import annotations

import threading

import pytest
from django.db import connection

from apps.core.models import IdSequence

pytestmark = pytest.mark.django_db


def test_allocation_starts_at_one():
    assert IdSequence.allocate("test:scope") == 1


def test_allocation_increments():
    scope = "test:scope"
    assert [IdSequence.allocate(scope) for _ in range(4)] == [1, 2, 3, 4]


def test_scopes_are_independent():
    assert IdSequence.allocate("faculty:a") == 1
    assert IdSequence.allocate("faculty:b") == 1
    assert IdSequence.allocate("faculty:a") == 2


def test_peek_does_not_consume():
    IdSequence.allocate("test:scope")
    assert IdSequence.peek("test:scope") == 1
    assert IdSequence.peek("test:scope") == 1
    assert IdSequence.allocate("test:scope") == 2


def test_peek_of_unknown_scope_is_zero():
    assert IdSequence.peek("never:used") == 0


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_concurrent_allocation_never_duplicates():
    """Eight threads competing for one scope must produce eight distinct values.

    `max(id) + 1` passes the sequential tests above and fails this one, which is
    exactly why the row lock exists.
    """
    scope = "test:concurrent"
    results: list[int] = []
    errors: list[Exception] = []
    lock = threading.Lock()
    start = threading.Barrier(8)

    def worker() -> None:
        try:
            start.wait(timeout=10)
            value = IdSequence.allocate(scope)
            with lock:
                results.append(value)
        except Exception as exc:  # pragma: no cover
            with lock:
                errors.append(exc)
        finally:
            # Each thread holds its own connection; leaving it open leaks it into
            # the test runner's teardown.
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, f"threads raised: {errors}"
    assert len(results) == 8
    assert len(set(results)) == 8, f"duplicate allocations: {sorted(results)}"
    assert sorted(results) == list(range(1, 9))
