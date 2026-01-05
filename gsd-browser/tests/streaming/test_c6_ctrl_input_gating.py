from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Any

import pytest

from gsd_browser.config import Settings
from gsd_browser.streaming.security import StreamingAuthConfig
from gsd_browser.streaming.server import DEFAULT_CTRL_NAMESPACE, create_streaming_app


def _run(value: Any) -> Any:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


def _require_input_handlers(runtime: Any, *, names: tuple[str, ...]) -> dict[str, Any]:
    handlers = runtime.sio.handlers.get(DEFAULT_CTRL_NAMESPACE) or {}
    missing = [name for name in names if name not in handlers]
    if missing:
        pytest.skip(f"C6 ctrl input handlers not implemented yet: {', '.join(missing)}")
    return handlers


def _make_auth_config(*, per_sid_events_per_minute: int = 120) -> StreamingAuthConfig:
    return StreamingAuthConfig(
        auth_required=False,
        api_key=None,
        allowed_origins=None,
        nonce_ttl_seconds=60,
        nonce_uses=4,
        per_sid_events_per_minute=per_sid_events_per_minute,
        per_sid_connects_per_minute=30,
    )


@dataclass
class _InputCase:
    event: str
    valid_payload: Any


_INPUT_CASES: list[_InputCase] = [
    _InputCase(
        event="input_click",
        valid_payload={"x": 10.5, "y": 20.25, "button": "left", "click_count": 1, "clickCount": 1},
    ),
    _InputCase(event="input_move", valid_payload={"x": 1, "y": 2}),
    _InputCase(
        event="input_wheel",
        valid_payload={"x": 1, "y": 2, "delta_x": 0, "delta_y": 120, "deltaX": 0, "deltaY": 120},
    ),
    _InputCase(event="input_keydown", valid_payload={"key": "a", "code": "KeyA"}),
    _InputCase(event="input_keyup", valid_payload={"key": "a", "code": "KeyA"}),
    _InputCase(event="input_type", valid_payload={"text": "hello"}),
]


def test_c6_holder_only_gating_is_preserved(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def _exercise() -> None:
        security_logger = logging.getLogger("test.security")
        security_logger.propagate = True

        monkeypatch.setattr(
            "gsd_browser.streaming.server.get_security_logger", lambda: security_logger
        )
        monkeypatch.setattr(
            "gsd_browser.streaming.server.load_streaming_auth_config", lambda: _make_auth_config()
        )
        caplog.set_level(logging.INFO, logger="test.security")

        runtime = create_streaming_app(settings=Settings())
        handlers = _require_input_handlers(
            runtime, names=tuple(item.event for item in _INPUT_CASES)
        )

        runtime.control_state.take_control(sid="holder")
        runtime.control_state.pause_if_holder(sid="holder")

        for item in _INPUT_CASES:
            caplog.clear()
            await handlers[item.event]("intruder", item.valid_payload)
            assert any(record.message == "ctrl_not_holder" for record in caplog.records)

    _run(_exercise())


def test_c6_paused_only_gating_is_preserved(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def _exercise() -> None:
        security_logger = logging.getLogger("test.security")
        security_logger.propagate = True

        monkeypatch.setattr(
            "gsd_browser.streaming.server.get_security_logger", lambda: security_logger
        )
        monkeypatch.setattr(
            "gsd_browser.streaming.server.load_streaming_auth_config", lambda: _make_auth_config()
        )
        caplog.set_level(logging.INFO, logger="test.security")

        runtime = create_streaming_app(settings=Settings())
        handlers = _require_input_handlers(runtime, names=("input_click",))

        runtime.control_state.take_control(sid="holder")
        runtime.control_state.resume_if_holder(sid="holder")
        assert runtime.control_state.is_paused() is False

        await handlers["input_click"]("holder", {"x": 10, "y": 20})
        assert any(record.message == "ctrl_not_paused" for record in caplog.records)

    _run(_exercise())
