from __future__ import annotations

import asyncio
import importlib
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest


def _run(value: Any) -> Any:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


@dataclass
class _CdpCall:
    method: str
    params: dict[str, Any]


class _FakeCdpClient:
    def __init__(self) -> None:
        self.calls: list[_CdpCall] = []

    async def send(self, method: str, params: dict[str, Any] | None = None) -> None:
        self.calls.append(_CdpCall(method=method, params=dict(params or {})))


def _require_o3b_dispatcher() -> Callable[[Any], Any]:
    try:
        module = importlib.import_module("gsd_browser.streaming.cdp_input_dispatch")
    except ModuleNotFoundError:
        pytest.skip("O3b CDP input dispatcher not implemented yet")

    dispatcher_cls = getattr(module, "CDPInputDispatcher", None)
    if dispatcher_cls is None:
        pytest.skip("O3b CDPInputDispatcher not implemented yet")

    def _construct(cdp_client: Any) -> Any:
        signature = inspect.signature(dispatcher_cls)
        if "cdp_client" in signature.parameters:
            return dispatcher_cls(cdp_client=cdp_client)
        return dispatcher_cls(cdp_client)

    return _construct


def _dispatcher_method(dispatcher: Any) -> Callable[[str, dict[str, Any]], Any]:
    for name in ("dispatch", "handle", "handle_event", "dispatch_event", "dispatch_input"):
        candidate = getattr(dispatcher, name, None)
        if callable(candidate):
            return candidate
    pytest.skip("O3b dispatcher has no supported dispatch method")


def _only_calls(fake: _FakeCdpClient, method: str) -> list[_CdpCall]:
    return [call for call in fake.calls if call.method == method]


def test_o3b_click_dispatches_mouse_pressed_then_released() -> None:
    async def _exercise() -> None:
        construct = _require_o3b_dispatcher()
        cdp = _FakeCdpClient()
        dispatcher = construct(cdp)
        dispatch = _dispatcher_method(dispatcher)

        await dispatch(
            "input_click",
            {"x": 10.5, "y": 20.25, "button": "left", "click_count": 2},
        )

        calls = _only_calls(cdp, "Input.dispatchMouseEvent")
        assert len(calls) == 2
        assert calls[0].params.get("type") == "mousePressed"
        assert calls[1].params.get("type") == "mouseReleased"

        for call in calls:
            assert call.params.get("x") == 10.5
            assert call.params.get("y") == 20.25
            assert call.params.get("button") == "left"
            assert call.params.get("clickCount") == 2

    _run(_exercise())


def test_o3b_wheel_dispatches_mouse_wheel_with_deltas() -> None:
    async def _exercise() -> None:
        construct = _require_o3b_dispatcher()
        cdp = _FakeCdpClient()
        dispatcher = construct(cdp)
        dispatch = _dispatcher_method(dispatcher)

        await dispatch(
            "input_wheel",
            {"x": 1.0, "y": 2.0, "delta_x": 0.0, "delta_y": 120.0},
        )

        calls = _only_calls(cdp, "Input.dispatchMouseEvent")
        assert len(calls) == 1
        params = calls[0].params
        assert params.get("type") == "mouseWheel"
        assert params.get("x") == 1.0
        assert params.get("y") == 2.0
        assert params.get("deltaX") == 0.0
        assert params.get("deltaY") == 120.0

    _run(_exercise())


def test_o3b_modifiers_shift_held_applies_to_following_key() -> None:
    async def _exercise() -> None:
        construct = _require_o3b_dispatcher()
        cdp = _FakeCdpClient()
        dispatcher = construct(cdp)
        dispatch = _dispatcher_method(dispatcher)

        await dispatch("input_keydown", {"key": "Shift", "code": "ShiftLeft"})
        await dispatch("input_keydown", {"key": "a", "code": "KeyA"})
        await dispatch("input_keyup", {"key": "a", "code": "KeyA"})
        await dispatch("input_keyup", {"key": "Shift", "code": "ShiftLeft"})

        calls = _only_calls(cdp, "Input.dispatchKeyEvent")
        assert calls, "expected Input.dispatchKeyEvent calls"

        a_down = next(
            (
                call
                for call in calls
                if call.params.get("type") in {"rawKeyDown", "keyDown"}
                and call.params.get("key") == "a"
            ),
            None,
        )
        assert a_down is not None, "expected a keyDown/rawKeyDown call"

        shift_bit = 8
        modifiers = a_down.params.get("modifiers")
        assert isinstance(modifiers, int)
        assert modifiers & shift_bit

    _run(_exercise())


def test_o3b_enter_sequence_has_down_then_up() -> None:
    async def _exercise() -> None:
        construct = _require_o3b_dispatcher()
        cdp = _FakeCdpClient()
        dispatcher = construct(cdp)
        dispatch = _dispatcher_method(dispatcher)

        await dispatch("input_keydown", {"key": "Enter", "code": "Enter"})
        await dispatch("input_keyup", {"key": "Enter", "code": "Enter"})

        calls = [
            call
            for call in _only_calls(cdp, "Input.dispatchKeyEvent")
            if call.params.get("key") == "Enter"
        ]
        assert len(calls) >= 2

        down_index = next(
            (
                idx
                for idx, call in enumerate(calls)
                if call.params.get("type") in {"rawKeyDown", "keyDown"}
            ),
            None,
        )
        up_index = next(
            (idx for idx, call in enumerate(calls) if call.params.get("type") == "keyUp"),
            None,
        )
        assert down_index is not None, "expected rawKeyDown/keyDown for Enter"
        assert up_index is not None, "expected keyUp for Enter"
        assert down_index < up_index, "expected Enter down before up"

    _run(_exercise())


def test_o3b_type_dispatches_char_events_that_round_trip_text() -> None:
    async def _exercise() -> None:
        construct = _require_o3b_dispatcher()
        cdp = _FakeCdpClient()
        dispatcher = construct(cdp)
        dispatch = _dispatcher_method(dispatcher)

        await dispatch("input_type", {"text": "aB!"})

        calls = _only_calls(cdp, "Input.dispatchKeyEvent")
        char_texts = [
            call.params.get("text") for call in calls if call.params.get("type") == "char"
        ]
        if not char_texts:
            pytest.fail("expected at least one char dispatchKeyEvent")
        assert "".join(text for text in char_texts if isinstance(text, str)) == "aB!"

    _run(_exercise())
