"""Provider implementations. Selected by settings, resolved lazily."""

from __future__ import annotations

from functools import cache

from django.conf import settings
from django.utils.module_loading import import_string

from apps.core.ports import NotificationProvider, PaymentProvider


@cache
def get_notification_provider() -> NotificationProvider:
    """Resolve `settings.NOTIFICATION_PROVIDER`.

    Swapping SMS aggregator is a settings change; no business logic mentions a
    vendor.
    """
    return import_string(settings.NOTIFICATION_PROVIDER)()


@cache
def get_payment_provider() -> PaymentProvider:
    """Resolve `settings.PAYMENT_PROVIDER` (mock until Phase 4)."""
    return import_string(settings.PAYMENT_PROVIDER)()


def reset_provider_cache() -> None:
    """Used by tests that override the provider settings."""
    get_notification_provider.cache_clear()
    get_payment_provider.cache_clear()
