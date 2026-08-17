"""
Per-request context (request id, acting user, client address).

The audit trail needs to attribute every change to somebody, but the code doing
the writing is usually a model or a service with no access to the request. A
thread-local set by middleware bridges that gap.

Actor resolution is deliberately *lazy*. With JWT the user is not resolved by
Django's AuthenticationMiddleware — DRF authenticates inside the view. Reading
`request.user` at middleware time would therefore see AnonymousUser on every API
call and silently mis-attribute the entire audit trail. So we stash the request
and read `.user` at write time, by which point DRF has assigned it (DRF's
`Request.user` setter also writes through to the underlying HttpRequest).
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

_state = threading.local()

SYSTEM_ACTOR_NAME = "system"


# ------------------------------------------------------------------ request id


def new_request_id() -> str:
    return uuid.uuid4().hex


def set_request_id(request_id: str) -> None:
    _state.request_id = request_id


def get_request_id() -> str | None:
    return getattr(_state, "request_id", None)


# ----------------------------------------------------------------- the request


def set_request(request: Any) -> None:
    _state.request = request


def get_request() -> Any | None:
    return getattr(_state, "request", None)


def get_client_ip() -> str | None:
    request = get_request()
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        # Left-most entry is the originating client.
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def get_user_agent() -> str:
    request = get_request()
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")[:400]


# ----------------------------------------------------------------------- actor


def set_actor(user: Any | None) -> None:
    """Pin an explicit actor — used by Celery tasks and management commands,
    which have no request to infer one from."""
    _state.actor = user


def get_actor() -> Any | None:
    explicit = getattr(_state, "actor", None)
    if explicit is not None:
        return explicit

    request = get_request()
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


@contextmanager
def acting_as(user: Any | None) -> Iterator[None]:
    """Attribute writes inside the block to `user`.

    Used by management commands and tasks so their changes are not recorded as
    anonymous. `acting_as(None)` records them as `system`.
    """
    previous = getattr(_state, "actor", None)
    _state.actor = user
    try:
        yield
    finally:
        _state.actor = previous


def clear() -> None:
    """Reset the context. Threads are reused between requests, so leaving a
    stale actor behind would attribute one user's change to another."""
    for attr in ("request_id", "request", "actor"):
        if hasattr(_state, attr):
            delattr(_state, attr)
