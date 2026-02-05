"""Per-session control state for take-control and pause/resume.

Extracted from server.py to break circular imports with session_registry.py.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

logger = logging.getLogger("gsd_browser.streaming")

DEFAULT_CTRL_NAMESPACE = "/ctrl"


def _get_security_logger() -> logging.Logger:
    """Lazy import to avoid circular dependency with security module."""
    from .security import get_security_logger

    return get_security_logger()


class ControlState:
    """Thread-safe control state shared across the dashboard thread and tool runtime."""

    def __init__(self, *, auto_pause_on_take_control: bool = True) -> None:
        self._lock = threading.Lock()
        self._unpaused = threading.Event()
        self._unpaused.set()

        self._auto_pause_on_take_control = bool(auto_pause_on_take_control)

        self.holder_sid: str | None = None
        self.held_since_ts: float | None = None
        self.paused: bool = False
        self.active_session_id: str | None = None
        self._input_events: list[dict[str, Any]] = []
        self._input_events_max = 1000
        self._input_seq = 0
        self._direct_dispatch_fn: Any = None
        self._dispatch_loop: asyncio.AbstractEventLoop | None = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "holder_sid": self.holder_sid,
                "held_since_ts": self.held_since_ts,
                "paused": self.paused,
                "active_session_id": self.active_session_id,
            }

    def set_active_session(self, *, session_id: str) -> None:
        session_id_value = str(session_id).strip()
        if not session_id_value:
            return
        with self._lock:
            if self.active_session_id != session_id_value:
                self._input_events.clear()
                self._input_seq = 0
            self.active_session_id = session_id_value

    def clear_active_session(self, *, session_id: str | None = None) -> None:
        with self._lock:
            if session_id is not None and self.active_session_id != session_id:
                return
            self.active_session_id = None
            self._input_events.clear()

    def has_active_session(self) -> bool:
        with self._lock:
            return self.active_session_id is not None

    def enqueue_input_event(
        self, *, sid: str, event: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        with self._lock:
            self._input_seq += 1
            record = {
                "seq": self._input_seq,
                "received_at": time.time(),
                "sid": sid,
                "event": event,
                "payload": payload,
            }
            self._input_events.append(record)
            dropped: dict[str, Any] | None = None
            if len(self._input_events) > self._input_events_max:
                dropped = self._input_events.pop(0)
            if dropped is not None:
                _get_security_logger().info(
                    "ctrl_input_dropped",
                    extra={
                        "namespace": DEFAULT_CTRL_NAMESPACE,
                        "sid": sid,
                        "event": event,
                        "dropped_seq": dropped.get("seq"),
                        "dropped_event": dropped.get("event"),
                        "queued": len(self._input_events),
                        "reason": "buffer_full",
                    },
                )
            if self._input_seq == 1 or self._input_seq % 25 == 0:
                meta: dict[str, Any] = {
                    "payload_keys": sorted(payload.keys()),
                }
                if event == "input_type":
                    text = payload.get("text")
                    if isinstance(text, str):
                        meta["text_len"] = len(text)
                _get_security_logger().info(
                    "ctrl_input_queued",
                    extra={
                        "namespace": DEFAULT_CTRL_NAMESPACE,
                        "sid": sid,
                        "event": event,
                        "seq": self._input_seq,
                        "queued": len(self._input_events),
                        **meta,
                    },
                )
            return {
                "queued": len(self._input_events),
                "dropped": dropped is not None,
            }

    def drain_input_events(
        self, *, max_items: int | None = None
    ) -> list[dict[str, Any]]:
        with self._lock:
            if max_items is None or max_items <= 0:
                drained = list(self._input_events)
                self._input_events.clear()
                return drained
            drained = self._input_events[:max_items]
            del self._input_events[:max_items]
            return drained

    def current_holder_sid(self) -> str | None:
        with self._lock:
            return self.holder_sid

    def is_holder(self, *, sid: str) -> bool:
        with self._lock:
            return self.holder_sid == sid

    def is_paused(self) -> bool:
        with self._lock:
            return self.paused

    def _set_paused_locked(self, paused: bool) -> None:
        self.paused = paused
        if paused:
            self._unpaused.clear()
        else:
            self._unpaused.set()

    def clear(self) -> None:
        with self._lock:
            self.holder_sid = None
            self.held_since_ts = None
            self._set_paused_locked(False)
            self._input_events.clear()

    def take_control(self, *, sid: str) -> None:
        with self._lock:
            if self.holder_sid is None:
                self.holder_sid = sid
                self.held_since_ts = time.time()
                self._input_events.clear()
                self._set_paused_locked(self._auto_pause_on_take_control)

    def release_control(self, *, sid: str) -> None:
        with self._lock:
            if self.holder_sid == sid:
                self.holder_sid = None
                self.held_since_ts = None
                self._set_paused_locked(False)

    def pause_if_holder(self, *, sid: str) -> bool:
        with self._lock:
            if self.holder_sid != sid:
                return False
            self._set_paused_locked(True)
            return True

    def resume_if_holder(self, *, sid: str) -> bool:
        with self._lock:
            if self.holder_sid != sid:
                return False
            self._set_paused_locked(False)
            return True

    def set_input_dispatcher(
        self,
        dispatch_fn: Any,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Register a direct CDP input dispatcher."""
        with self._lock:
            self._direct_dispatch_fn = dispatch_fn
            self._dispatch_loop = loop

    def clear_input_dispatcher(self) -> None:
        with self._lock:
            self._direct_dispatch_fn = None
            self._dispatch_loop = None

    async def dispatch_input_directly(
        self, event: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Dispatch an input event directly to CDP."""
        with self._lock:
            fn = getattr(self, "_direct_dispatch_fn", None)
            loop = getattr(self, "_dispatch_loop", None)
        if fn is None or loop is None:
            logger.debug(
                "dispatch_input_directly: no dispatcher (fn=%s, loop=%s)",
                fn is not None,
                loop is not None,
            )
            return {"ok": False, "error": "no_dispatcher"}
        try:
            future = asyncio.run_coroutine_threadsafe(
                fn(event, payload), loop
            )
            await asyncio.wrap_future(future)
        except Exception as exc:
            logger.warning(
                "dispatch_input_directly failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            return {
                "ok": False,
                "error": f"dispatch_error: {type(exc).__name__}",
            }
        logger.debug("dispatch_input_directly: OK event=%s", event)
        return {"ok": True}

    async def wait_until_unpaused(self) -> None:
        if not self.is_paused():
            return
        await asyncio.to_thread(self._unpaused.wait)
