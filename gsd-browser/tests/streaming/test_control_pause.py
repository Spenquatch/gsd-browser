from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any

import pytest

from gsd_browser.config import Settings
from gsd_browser.streaming.server import (
    DEFAULT_CTRL_NAMESPACE,
    ControlState,
    create_streaming_app,
)


def _run(value: Any) -> Any:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


async def _yield_loop(*, ticks: int = 3) -> None:
    for _ in range(ticks):
        await asyncio.sleep(0)


def test_control_state_holder_semantics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gsd_browser.streaming.server.time.time", lambda: 123.0)

    state = ControlState()
    assert state.snapshot() == {
        "holder_sid": None,
        "held_since_ts": None,
        "paused": False,
        "active_session_id": None,
    }

    state.take_control(sid="sid-1")
    assert state.snapshot() == {
        "holder_sid": "sid-1",
        "held_since_ts": 123.0,
        "paused": True,
        "active_session_id": None,
    }

    state.take_control(sid="sid-2")
    assert state.snapshot() == {
        "holder_sid": "sid-1",
        "held_since_ts": 123.0,
        "paused": True,
        "active_session_id": None,
    }

    assert state.pause_if_holder(sid="sid-2") is False
    assert state.snapshot() == {
        "holder_sid": "sid-1",
        "held_since_ts": 123.0,
        "paused": True,
        "active_session_id": None,
    }

    assert state.pause_if_holder(sid="sid-1") is True
    assert state.snapshot() == {
        "holder_sid": "sid-1",
        "held_since_ts": 123.0,
        "paused": True,
        "active_session_id": None,
    }

    assert state.resume_if_holder(sid="sid-2") is False
    assert state.snapshot() == {
        "holder_sid": "sid-1",
        "held_since_ts": 123.0,
        "paused": True,
        "active_session_id": None,
    }

    assert state.resume_if_holder(sid="sid-1") is True
    assert state.snapshot() == {
        "holder_sid": "sid-1",
        "held_since_ts": 123.0,
        "paused": False,
        "active_session_id": None,
    }

    state.release_control(sid="sid-2")
    assert state.snapshot() == {
        "holder_sid": "sid-1",
        "held_since_ts": 123.0,
        "paused": False,
        "active_session_id": None,
    }

    state.release_control(sid="sid-1")
    assert state.snapshot() == {
        "holder_sid": None,
        "held_since_ts": None,
        "paused": False,
        "active_session_id": None,
    }


def test_control_state_clear_unpauses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gsd_browser.streaming.server.time.time", lambda: 123.0)

    state = ControlState()
    state.take_control(sid="sid-1")
    assert state.pause_if_holder(sid="sid-1") is True
    assert state.snapshot()["paused"] is True

    state.clear()
    assert state.snapshot() == {
        "holder_sid": None,
        "held_since_ts": None,
        "paused": False,
        "active_session_id": None,
    }


def test_control_state_wait_until_unpaused_noop_when_running() -> None:
    async def _exercise() -> None:
        state = ControlState()
        await state.wait_until_unpaused()

    _run(_exercise())


def test_control_state_wait_until_unpaused_blocks_then_resumes() -> None:
    async def _exercise() -> None:
        state = ControlState()
        state.take_control(sid="sid-1")
        assert state.pause_if_holder(sid="sid-1") is True

        waiter = asyncio.create_task(state.wait_until_unpaused())
        try:
            await _yield_loop()
            assert waiter.done() is False

            assert state.resume_if_holder(sid="sid-2") is False
            await _yield_loop()
            assert waiter.done() is False

            assert state.resume_if_holder(sid="sid-1") is True
            await asyncio.wait_for(waiter, timeout=1.0)
        finally:
            state.clear()
            await _yield_loop()
            if not waiter.done():
                await asyncio.wait_for(waiter, timeout=1.0)

    _run(_exercise())


class _EmitCapture:
    def __init__(self) -> None:
        self.emits: list[dict[str, Any]] = []

    async def emit(
        self,
        event: str,
        payload: dict[str, Any],
        *,
        namespace: str | None = None,
        to: str | None = None,
        **_: Any,
    ) -> None:
        self.emits.append({"event": event, "payload": payload, "namespace": namespace, "to": to})


def test_ctrl_socket_handlers_enforce_holder_and_publish_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _exercise() -> None:
        monkeypatch.setattr("gsd_browser.streaming.server.time.time", lambda: 123.0)
        monkeypatch.setattr(
            "gsd_browser.streaming.server.get_security_logger",
            lambda: logging.getLogger("test.security"),
        )
        monkeypatch.setattr(
            "gsd_browser.streaming.server.authorize_socket_connection",
            lambda **_: True,
        )

        runtime = create_streaming_app(settings=Settings(auto_pause_on_take_control=False))
        capture = _EmitCapture()
        monkeypatch.setattr(runtime.sio, "emit", capture.emit)

        handlers = runtime.sio.handlers[DEFAULT_CTRL_NAMESPACE]

        await handlers["connect_ctrl"]("sid-1", {}, None)
        assert capture.emits[-1] == {
            "event": "control_state",
            "payload": {
                "holder_sid": None,
                "held_since_ts": None,
                "paused": False,
                "active_session_id": None,
            },
            "namespace": DEFAULT_CTRL_NAMESPACE,
            "to": "sid-1",
        }

        await handlers["take_control"]("sid-1", {})
        assert capture.emits[-1]["payload"] == {
            "holder_sid": "sid-1",
            "held_since_ts": 123.0,
            "paused": False,
            "active_session_id": None,
        }

        await handlers["pause_agent"]("sid-2", {})
        assert capture.emits[-1]["payload"]["paused"] is False

        await handlers["pause_agent"]("sid-1", {})
        assert capture.emits[-1]["payload"]["paused"] is True

        await handlers["release_control"]("sid-1", {})
        assert capture.emits[-1]["payload"] == {
            "holder_sid": None,
            "held_since_ts": None,
            "paused": False,
            "active_session_id": None,
        }

    _run(_exercise())


def test_ctrl_disconnect_clears_pause(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _exercise() -> None:
        monkeypatch.setattr("gsd_browser.streaming.server.time.time", lambda: 123.0)
        monkeypatch.setattr(
            "gsd_browser.streaming.server.get_security_logger",
            lambda: logging.getLogger("test.security"),
        )
        monkeypatch.setattr(
            "gsd_browser.streaming.server.authorize_socket_connection",
            lambda **_: True,
        )

        runtime = create_streaming_app(settings=Settings())
        capture = _EmitCapture()
        monkeypatch.setattr(runtime.sio, "emit", capture.emit)

        handlers = runtime.sio.handlers[DEFAULT_CTRL_NAMESPACE]

        await handlers["take_control"]("sid-1", {})
        await handlers["pause_agent"]("sid-1", {})
        assert capture.emits[-1]["payload"]["paused"] is True

        await handlers["disconnect_ctrl"]("sid-1")
        assert capture.emits[-1]["payload"] == {
            "holder_sid": None,
            "held_since_ts": None,
            "paused": False,
            "active_session_id": None,
        }

    _run(_exercise())
