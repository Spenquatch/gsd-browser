from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from .identity import Identity

_current_identity: ContextVar[Identity | None] = ContextVar(  # type: ignore[assignment]
    "gsd_identity",
    default=None,
)


@contextmanager
def identity_scope(identity: Identity) -> Iterator[Identity]:
    token = _current_identity.set(identity)
    try:
        yield identity
    finally:
        _current_identity.reset(token)


def get_current_identity() -> Identity | None:
    return _current_identity.get()


def require_current_identity() -> Identity:
    identity = get_current_identity()
    if identity is None:
        raise RuntimeError("No current identity set")
    return identity
