from __future__ import annotations

import asyncio
import inspect
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from gsd_browser import mcp_server as mcp_server_mod


def _assert_uuid(value: str) -> None:
    parsed = uuid.UUID(value)
    assert str(parsed) == value


async def _maybe_await(value: Any) -> None:
    if inspect.isawaitable(value):
        await value


def _parse_payload(response: list[Any]) -> dict[str, Any]:
    assert isinstance(response, list)
    assert len(response) == 1
    assert getattr(response[0], "type", None) == "text"
    payload = json.loads(getattr(response[0], "text", ""))
    assert isinstance(payload, dict)
    return payload


class _DummyScreenshotManager:
    def __init__(self) -> None:
        self.current_session_id: str | None = None
        self.current_session_start: float | None = None

    def record_screenshot(self, **_: Any) -> None:  # type: ignore[no-untyped-def]
        return None

    async def add_key_screenshot(self, *_: Any, **__: Any) -> dict[str, Any]:
        return {"id": "dummy"}


class _DummyRuntime:
    def __init__(self, *, screenshots: _DummyScreenshotManager, control_state: Any) -> None:
        self.screenshots = screenshots
        self._dashboard_runtime = type("_DashRt", (), {"control_state": control_state})()

    def ensure_dashboard_running(self, *_: Any, **__: Any) -> None:
        return None

    def dashboard(self) -> Any:
        return type("_Dash", (), {"runtime": self._dashboard_runtime})()


class _DummyHistory:
    history: list[object] = []

    def final_result(self) -> str | None:
        return "ok"

    def has_errors(self) -> bool:
        return False

    def errors(self) -> list[object]:
        return []


@dataclass
class _StepInfo:
    step: int
    url: str
    screenshot: str = "aW1n"  # base64("img")

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


class _C6Agent:
    created: list[_C6Agent] = []
    control_state: Any | None = None

    def __init__(self, *_: Any, **kwargs: Any) -> None:
        self._step_callback: Callable[..., Any] | None = None
        for key in (
            "register_new_step_callback",
            "new_step_callback",
            "on_step_end",
            "step_callback",
        ):
            candidate = kwargs.get(key)
            if callable(candidate):
                self._step_callback = candidate
                break
        type(self).created.append(self)

    def register_new_step_callback(self, callback: Callable[..., Any]) -> None:
        self._step_callback = callback

    async def _invoke_callback(self, info: _StepInfo) -> None:
        if self._step_callback is None:
            return
        try:
            await _maybe_await(self._step_callback(info, None, info.step))
        except TypeError:
            try:
                await _maybe_await(self._step_callback(info))
            except TypeError:
                await _maybe_await(self._step_callback())

    async def run(self, *args: Any, **kwargs: Any) -> _DummyHistory:
        on_step_end = kwargs.get("on_step_end")

        step1 = _StepInfo(step=1, url="https://example.com")
        step2 = _StepInfo(step=2, url="https://example.com")

        await self._invoke_callback(step1)

        control_state = type(self).control_state
        if control_state is not None:
            control_state.pause()

        await asyncio.sleep(0)
        if callable(on_step_end):
            await _maybe_await(on_step_end(step1))

        await self._invoke_callback(step2)
        if callable(on_step_end):
            await _maybe_await(on_step_end(step2))
        return _DummyHistory()


class _C6ControlState:
    def __init__(self) -> None:
        self.paused = False
        self.active_session_id: str | None = None
        self._unpaused = asyncio.Event()
        self._unpaused.set()
        self._events: list[dict[str, Any]] = []
        self._drain_calls = 0

    def set_active_session(self, *, session_id: str) -> None:
        self.active_session_id = str(session_id)

    def pause(self) -> None:
        self.paused = True
        self._unpaused.clear()

    def resume(self) -> None:
        self.paused = False
        self._unpaused.set()

    def is_paused(self) -> bool:
        return bool(self.paused)

    async def wait_until_unpaused(self) -> None:
        if not self.paused:
            return
        await self._unpaused.wait()

    def enqueue(self, record: dict[str, Any]) -> None:
        self._events.append(dict(record))

    def drain_input_events(self, *, max_items: int | None = None) -> list[dict[str, Any]]:
        if max_items is None:
            drained = list(self._events)
            self._events.clear()
            return drained

        self._drain_calls += 1
        if self._drain_calls == 1 and self._events:
            drained = [self._events.pop(0)]
            self.resume()
            return drained
        return []


class _DispatchRecorder:
    dispatched: list[tuple[str, dict[str, Any]]] = []

    def __init__(self, *_: Any, **__: Any) -> None:
        return None

    async def dispatch(self, event: str, payload: dict[str, Any]) -> None:
        type(self).dispatched.append((event, dict(payload)))


class _BrowserSessionWithCdpClient:
    def __init__(self, *_: Any, **__: Any) -> None:
        self.cdp_client = object()


def test_c6_resume_does_not_replay_stale_buffered_inputs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    screenshots = _DummyScreenshotManager()
    control_state = _C6ControlState()
    runtime = _DummyRuntime(screenshots=screenshots, control_state=control_state)

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: runtime)
    monkeypatch.setattr(mcp_server_mod, "load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        mcp_server_mod,
        "create_browser_use_llms",
        lambda *args, **kwargs: type("DummyLLMs", (), {"primary": object(), "fallback": None})(),
    )
    monkeypatch.setattr(mcp_server_mod, "CDPInputDispatcher", _DispatchRecorder)
    monkeypatch.setattr(
        mcp_server_mod,
        "_load_browser_use_classes",
        lambda: (_C6Agent, _BrowserSessionWithCdpClient),
    )
    monkeypatch.setattr(
        mcp_server_mod, "get_security_logger", lambda: logging.getLogger("test"), raising=False
    )

    _C6Agent.created.clear()
    _C6Agent.control_state = control_state
    _DispatchRecorder.dispatched.clear()

    control_state.enqueue({"event": "input_move", "payload": {"x": 1.0, "y": 2.0}})
    control_state.enqueue({"event": "input_type", "payload": {"text": "stale"}})

    caplog.set_level(logging.INFO, logger="gsd_browser.mcp")
    response = asyncio.run(
        mcp_server_mod.web_eval_agent(
            url="example.com",
            task="do something",
            ctx=object(),
            headless_browser=True,
        )
    )
    payload = _parse_payload(response)

    _assert_uuid(payload["session_id"])
    assert _DispatchRecorder.dispatched == [("input_move", {"x": 1.0, "y": 2.0})]

    assert any(
        record.message == "ctrl_input_dropped"
        and getattr(record, "dropped", None) == 1
        and getattr(record, "reason", None) == "resumed"
        for record in caplog.records
    )


class _FailOnceCdpClient:
    def __init__(self, *, fail_first: bool) -> None:
        self._fail_first = fail_first
        self.calls: list[tuple[str, str]] = []

    async def send(self, method: str, params: dict[str, Any] | None = None, **kwargs: Any) -> None:
        session_id = str(kwargs.get("session_id") or "")
        self.calls.append((method, session_id))
        if self._fail_first:
            self._fail_first = False
            raise RuntimeError("detached")


@dataclass
class _FakeCdpSession:
    session_id: str
    cdp_client: Any


class _C6BrowserSession:
    created: list[_C6BrowserSession] = []

    def __init__(self, *_: Any, **__: Any) -> None:
        self._calls = 0
        self.sessions = [
            _FakeCdpSession(session_id="cdp-A", cdp_client=_FailOnceCdpClient(fail_first=True)),
            _FakeCdpSession(session_id="cdp-B", cdp_client=_FailOnceCdpClient(fail_first=False)),
        ]
        type(self).created.append(self)

    def get_or_create_cdp_session(self) -> _FakeCdpSession:
        idx = min(self._calls, len(self.sessions) - 1)
        self._calls += 1
        return self.sessions[idx]


def _require_c6_target_dispatch_support() -> None:
    try:
        from gsd_browser.streaming import cdp_input_dispatch as cdp_mod
    except Exception as exc:  # noqa: BLE001
        pytest.xfail(f"C6 CDP dispatch module unavailable: {exc}")

    try:
        dispatcher_cls = cdp_mod.CDPInputDispatcher
    except AttributeError as exc:
        pytest.xfail(f"C6 CDP dispatch module unavailable: {exc}")

    dispatcher_sig = inspect.signature(dispatcher_cls)
    if "send" not in dispatcher_sig.parameters:
        pytest.xfail("C6 CDPInputDispatcher(send=...) not implemented yet")

    src = inspect.getsource(mcp_server_mod.web_eval_agent)
    if "get_or_create_cdp_session" not in src:
        pytest.xfail("C6 web_eval_agent target re-acquisition not implemented yet")


def test_c6_reacquires_target_when_dispatch_errors_simulate_detach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_c6_target_dispatch_support()

    screenshots = _DummyScreenshotManager()
    control_state = _C6ControlState()
    runtime = _DummyRuntime(screenshots=screenshots, control_state=control_state)

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: runtime)
    monkeypatch.setattr(mcp_server_mod, "load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        mcp_server_mod,
        "create_browser_use_llms",
        lambda *args, **kwargs: type("DummyLLMs", (), {"primary": object(), "fallback": None})(),
    )
    monkeypatch.setattr(
        mcp_server_mod, "_load_browser_use_classes", lambda: (_C6Agent, _C6BrowserSession)
    )
    monkeypatch.setattr(
        mcp_server_mod, "get_security_logger", lambda: logging.getLogger("test"), raising=False
    )

    real_sleep = asyncio.sleep

    async def _fast_sleep(_: float) -> None:
        await real_sleep(0)

    monkeypatch.setattr(mcp_server_mod.asyncio, "sleep", _fast_sleep)

    _C6Agent.created.clear()
    _C6Agent.control_state = control_state
    _C6BrowserSession.created.clear()

    control_state.enqueue({"event": "input_move", "payload": {"x": 1.0, "y": 2.0}})

    response = asyncio.run(
        mcp_server_mod.web_eval_agent(
            url="example.com",
            task="do something",
            ctx=object(),
            headless_browser=True,
        )
    )
    payload = _parse_payload(response)
    _assert_uuid(payload["session_id"])

    assert _C6BrowserSession.created, "expected BrowserSession to be constructed"
    browser_session = _C6BrowserSession.created[0]

    assert browser_session._calls >= 2, "expected get_or_create_cdp_session retry on detach"
    first_client = browser_session.sessions[0].cdp_client
    second_client = browser_session.sessions[1].cdp_client
    assert isinstance(first_client, _FailOnceCdpClient)
    assert isinstance(second_client, _FailOnceCdpClient)
    assert first_client.calls == [("Input.dispatchMouseEvent", "cdp-A")]
    assert second_client.calls == [("Input.dispatchMouseEvent", "cdp-B")]
