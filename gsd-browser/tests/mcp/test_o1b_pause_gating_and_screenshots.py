from __future__ import annotations

import asyncio
import inspect
import json
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


@dataclass
class _StepInfo:
    step: int
    url: str
    screenshot: str = "aW1n"  # base64("img")

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


class _DummyControlState:
    def __init__(self) -> None:
        self.paused = False
        self.wait_calls = 0
        self.wait_started = asyncio.Event()
        self._unpaused = asyncio.Event()
        self._unpaused.set()

    def pause(self) -> None:
        self.paused = True
        self.wait_started.clear()
        self._unpaused.clear()

    def resume(self) -> None:
        self.paused = False
        self._unpaused.set()

    async def wait_until_unpaused(self) -> None:
        if not self.paused:
            return
        self.wait_calls += 1
        self.wait_started.set()
        await self._unpaused.wait()


class _DummyScreenshotManager:
    def __init__(self) -> None:
        self.current_session_id: str | None = None
        self.current_session_start: float | None = None
        self.record_calls: list[dict[str, Any]] = []
        self.add_key_calls: list[dict[str, Any]] = []

    def record_screenshot(self, **kwargs: Any) -> None:  # type: ignore[no-untyped-def]
        self.record_calls.append(dict(kwargs))

    async def add_key_screenshot(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.add_key_calls.append({"args": args, "kwargs": dict(kwargs)})
        return {"id": "dummy"}


class _DummyRuntime:
    def __init__(
        self, *, screenshots: _DummyScreenshotManager, control_state: _DummyControlState
    ) -> None:
        self.screenshots = screenshots
        self._dashboard_runtime = type("_DashRt", (), {"control_state": control_state})()

    def ensure_dashboard_running(self, *args: Any, **kwargs: Any) -> None:
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


class _DummyAgent:
    created: list[_DummyAgent] = []
    shared_control_state: _DummyControlState | None = None
    pause_between_steps: bool = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._step_callback: Callable[..., Any] | None = None
        self._registered_callback = False

        for key in (
            "register_new_step_callback",
            "new_step_callback",
            "on_step_end",
            "step_callback",
        ):
            candidate = kwargs.get(key)
            if callable(candidate):
                self._step_callback = candidate
                self._registered_callback = True
                break

        self.browser_session = kwargs.get("browser_session")
        _DummyAgent.created.append(self)

    def register_new_step_callback(self, callback: Callable[..., Any]) -> None:
        self._step_callback = callback
        self._registered_callback = True

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
        control_state = type(self).shared_control_state
        on_step_end = kwargs.get("on_step_end")

        step1 = _StepInfo(step=1, url="https://example.com")
        step2 = _StepInfo(step=2, url="https://example.com")

        await self._invoke_callback(step1)

        if control_state is not None and type(self).pause_between_steps:
            control_state.pause()

        if callable(on_step_end):
            await _maybe_await(on_step_end(step1))

        await self._invoke_callback(step2)

        if callable(on_step_end):
            await _maybe_await(on_step_end(step2))

        return _DummyHistory()


class _DummyBrowserSession:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        return None


def _run(value: Any) -> Any:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


def _parse_payload(response: list[Any]) -> dict[str, Any]:
    assert isinstance(response, list)
    assert len(response) == 1
    assert getattr(response[0], "type", None) == "text"
    payload = json.loads(getattr(response[0], "text", ""))
    assert isinstance(payload, dict)
    return payload


def test_o1b_records_agent_step_screenshots_and_updates_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screenshots = _DummyScreenshotManager()
    control_state = _DummyControlState()
    runtime = _DummyRuntime(screenshots=screenshots, control_state=control_state)

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: runtime)
    monkeypatch.setattr(mcp_server_mod, "load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr(mcp_server_mod, "create_browser_use_llm", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        mcp_server_mod, "_load_browser_use_classes", lambda: (_DummyAgent, _DummyBrowserSession)
    )

    _DummyAgent.created.clear()
    _DummyAgent.shared_control_state = control_state
    _DummyAgent.pause_between_steps = False
    response = _run(
        mcp_server_mod.web_eval_agent(
            url="example.com",
            task="do something",
            ctx=object(),
            headless_browser=True,
        )
    )
    payload = _parse_payload(response)

    assert _DummyAgent.created, "expected Agent to be constructed"
    agent = _DummyAgent.created[0]
    assert agent._registered_callback, "expected step callback to be registered"

    _assert_uuid(payload["session_id"])
    _assert_uuid(payload["tool_call_id"])

    artifacts = payload.get("artifacts") or {}
    assert isinstance(artifacts, dict)
    assert int(artifacts.get("screenshots", 0)) > 0

    next_actions = payload.get("next_actions") or []
    assert isinstance(next_actions, list)
    assert any("get_screenshots" in str(item) for item in next_actions)

    assert (
        any(call.get("screenshot_type") == "agent_step" for call in screenshots.record_calls)
        or screenshots.add_key_calls
    )


def test_o1b_pause_gate_blocks_between_steps_until_resumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screenshots = _DummyScreenshotManager()
    control_state = _DummyControlState()
    runtime = _DummyRuntime(screenshots=screenshots, control_state=control_state)

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: runtime)
    monkeypatch.setattr(mcp_server_mod, "load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr(mcp_server_mod, "create_browser_use_llm", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        mcp_server_mod, "_load_browser_use_classes", lambda: (_DummyAgent, _DummyBrowserSession)
    )

    _DummyAgent.created.clear()
    _DummyAgent.shared_control_state = control_state
    _DummyAgent.pause_between_steps = True

    async def scenario() -> list[Any]:
        task = asyncio.create_task(
            mcp_server_mod.web_eval_agent(
                url="example.com",
                task="do something",
                ctx=object(),
                headless_browser=True,
            )
        )
        try:
            await asyncio.wait_for(control_state.wait_started.wait(), timeout=0.25)
        except TimeoutError:
            raise

        assert not task.done(), "expected web_eval_agent to block while paused"
        control_state.resume()
        return await asyncio.wait_for(task, timeout=0.5)

    response = asyncio.run(scenario())
    payload = _parse_payload(response)

    assert control_state.wait_calls >= 1
    assert payload["status"] in ("success", "partial", "failed")
