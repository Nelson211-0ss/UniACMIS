"""
Provider registry — the mechanism behind the ports in `apps.core.ports`.

Modules register implementations at `AppConfig.ready()`; callers resolve by
interface. Nothing here imports a domain app, which is what keeps the dependency
direction inverted (ARCHITECTURE §4, rule 3).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[Any, list[Any]] = {}

    def register(self, interface: Any, provider: Any | None = None) -> Any:
        """Register an implementation, directly or as a class decorator.

        registry.register(HoldProvider, FeeBalanceHoldProvider())

        @registry.register(HoldProvider)
        class FeeBalanceHoldProvider: ...
        """
        if provider is None:

            def decorator(cls: Callable[..., T]) -> Callable[..., T]:
                self._add(interface, cls())
                return cls

            return decorator

        self._add(interface, provider)
        return provider

    def _add(self, interface: Any, provider: Any) -> None:
        bucket = self._providers.setdefault(interface, [])
        # Replace any existing instance of the same class. AppConfig.ready() can
        # run more than once (notably under the test runner), and duplicate
        # providers would double-count holds or send an SMS twice.
        bucket[:] = [p for p in bucket if type(p) is not type(provider)]
        bucket.append(provider)

    def get_all(self, interface: Any) -> list[Any]:
        return list(self._providers.get(interface, []))

    def get(self, interface: Any) -> Any | None:
        """The single implementation, or None. Last registration wins."""
        bucket = self._providers.get(interface)
        return bucket[-1] if bucket else None

    def unregister(self, interface: Any, provider_class: type) -> None:
        bucket = self._providers.get(interface, [])
        bucket[:] = [p for p in bucket if type(p) is not provider_class]

    def clear(self, interface: Any | None = None) -> None:
        """Reset — used by tests that need an isolated registry."""
        if interface is None:
            self._providers.clear()
        else:
            self._providers.pop(interface, None)


registry = ProviderRegistry()
