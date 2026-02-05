from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_PROPAGATE_CANCELLED_ERROR: ContextVar[bool] = ContextVar(
    "gsd_optionb_propagate_cancelled_error", default=False
)


@contextmanager
def propagate_cancelled_error() -> Iterator[None]:
    token = _PROPAGATE_CANCELLED_ERROR.set(True)
    try:
        yield
    finally:
        _PROPAGATE_CANCELLED_ERROR.reset(token)


def should_propagate_cancelled_error() -> bool:
    return bool(_PROPAGATE_CANCELLED_ERROR.get())
