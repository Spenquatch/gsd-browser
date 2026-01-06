from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from gsd_browser import mcp_server as mcp_server_mod
from gsd_browser.screenshot_manager import ScreenshotManager


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


def _web_eval_agent_source() -> str:
    try:
        return inspect.getsource(mcp_server_mod.web_eval_agent)
    except Exception:  # noqa: BLE001
        return ""


def _record_step_screenshot_has_fallback() -> bool:
    src = _web_eval_agent_source()
    return ".get_current_page" in src or "get_current_page(" in src


def _record_step_screenshot_includes_source_metadata() -> bool:
    src = _web_eval_agent_source()
    return "current_page_fallback" in src or '"source"' in src or "'source'" in src


@dataclass
class _StepInfo:
    step: int
    url: str
    title: str
    screenshot: str | None = None

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


class _DummyScreenshotManager:
    def __init__(self) -> None:
        self.current_session_id: str | None = None
        self.current_session_start: float | None = None
        self.record_calls: list[dict[str, Any]] = []

    def record_screenshot(self, **kwargs: Any) -> None:  # type: ignore[no-untyped-def]
        self.record_calls.append(dict(kwargs))


class _DummyRuntime:
    def __init__(self, *, screenshots: _DummyScreenshotManager) -> None:
        self.screenshots = screenshots
        self._dashboard_runtime = type(
            "_DashRt", (), {"control_state": type("_Ctrl", (), {"paused": False})()}
        )()

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
    screenshot_value: str | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
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
        _DummyAgent.created.append(self)

    def register_new_step_callback(self, callback: Callable[..., Any]) -> None:
        self._step_callback = callback

    async def run(self, *args: Any, **kwargs: Any) -> _DummyHistory:
        info = _StepInfo(
            step=1,
            url="https://example.com",
            title="Example",
            screenshot=type(self).screenshot_value,
        )
        if self._step_callback is not None:
            try:
                result = self._step_callback(info, None, info.step)
                if inspect.isawaitable(result):
                    await result
            except TypeError:
                result = self._step_callback(info)
                if inspect.isawaitable(result):
                    await result
        return _DummyHistory()


class _DummyPage:
    def __init__(self, *, should_raise: bool) -> None:
        self.should_raise = should_raise
        self.calls: list[dict[str, Any]] = []

    async def screenshot(self, *args: Any, **kwargs: Any) -> bytes:
        self.calls.append({"args": args, "kwargs": dict(kwargs)})
        if self.should_raise:
            raise RuntimeError("boom")
        return b"img"


class _DummyBrowserSession:
    created: list[_DummyBrowserSession] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.page = _DummyPage(should_raise=bool(kwargs.get("should_raise")))
        self.get_current_page_calls = 0
        type(self).created.append(self)

    async def get_current_page(self) -> _DummyPage:
        self.get_current_page_calls += 1
        return self.page


def test_c3_fallback_capture_attempted_when_summary_screenshot_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not _record_step_screenshot_has_fallback():
        pytest.xfail("C3 fallback capture not implemented in this branch yet")
    if not _record_step_screenshot_includes_source_metadata():
        pytest.xfail("C3 screenshot source metadata not implemented in this branch yet")

    screenshots = _DummyScreenshotManager()
    runtime = _DummyRuntime(screenshots=screenshots)

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: runtime)
    monkeypatch.setattr(mcp_server_mod, "load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        mcp_server_mod,
        "create_browser_use_llms",
        lambda *args, **kwargs: type("DummyLLMs", (), {"primary": object(), "fallback": None})(),
    )
    monkeypatch.setattr(
        mcp_server_mod, "_load_browser_use_classes", lambda: (_DummyAgent, _DummyBrowserSession)
    )

    _DummyAgent.created.clear()
    _DummyAgent.screenshot_value = None
    _DummyBrowserSession.created.clear()
    response = _run(
        mcp_server_mod.web_eval_agent(
            url="example.com",
            task="do something",
            ctx=object(),
            headless_browser=True,
        )
    )
    payload = _parse_payload(response)
    assert payload["status"] in ("success", "partial", "failed")

    assert _DummyAgent.created, "expected Agent to be constructed"
    assert _DummyBrowserSession.created, "expected BrowserSession to be constructed"
    assert _DummyBrowserSession.created[0].get_current_page_calls >= 1
    assert screenshots.record_calls, "expected fallback to record an agent_step screenshot"

    call = screenshots.record_calls[0]
    assert call.get("screenshot_type") == "agent_step"
    assert call.get("session_id"), "expected session_id on recorded screenshot"
    assert isinstance(call.get("captured_at"), (int, float))
    assert call.get("step") == 1
    assert call.get("url") == "https://example.com"

    metadata = call.get("metadata") or {}
    assert metadata.get("title") == "Example"
    assert metadata.get("source") == "current_page_fallback"


def test_c3_fallback_capture_failure_does_not_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not _record_step_screenshot_has_fallback():
        pytest.xfail("C3 fallback capture not implemented in this branch yet")

    screenshots = _DummyScreenshotManager()
    runtime = _DummyRuntime(screenshots=screenshots)

    def _browser_use_classes() -> tuple[type[_DummyAgent], type[_DummyBrowserSession]]:
        class RaisingSession(_DummyBrowserSession):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)
                self.page.should_raise = True

        return _DummyAgent, RaisingSession

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: runtime)
    monkeypatch.setattr(mcp_server_mod, "load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        mcp_server_mod,
        "create_browser_use_llms",
        lambda *args, **kwargs: type("DummyLLMs", (), {"primary": object(), "fallback": None})(),
    )
    monkeypatch.setattr(mcp_server_mod, "_load_browser_use_classes", _browser_use_classes)

    _DummyAgent.created.clear()
    _DummyAgent.screenshot_value = None
    response = _run(
        mcp_server_mod.web_eval_agent(
            url="example.com",
            task="do something",
            ctx=object(),
            headless_browser=True,
        )
    )
    payload = _parse_payload(response)
    assert payload["status"] in ("success", "partial", "failed")


def test_c3_summary_screenshot_records_source_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not _record_step_screenshot_includes_source_metadata():
        pytest.xfail("C3 screenshot source metadata not implemented in this branch yet")

    screenshots = _DummyScreenshotManager()
    runtime = _DummyRuntime(screenshots=screenshots)

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: runtime)
    monkeypatch.setattr(mcp_server_mod, "load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        mcp_server_mod,
        "create_browser_use_llms",
        lambda *args, **kwargs: type("DummyLLMs", (), {"primary": object(), "fallback": None})(),
    )
    monkeypatch.setattr(
        mcp_server_mod, "_load_browser_use_classes", lambda: (_DummyAgent, _DummyBrowserSession)
    )

    _DummyAgent.created.clear()
    _DummyAgent.screenshot_value = "aW1n"  # base64("img")
    response = _run(
        mcp_server_mod.web_eval_agent(
            url="example.com",
            task="do something",
            ctx=object(),
            headless_browser=True,
        )
    )
    payload = _parse_payload(response)
    assert payload["status"] in ("success", "partial", "failed")

    assert screenshots.record_calls, (
        "expected summary screenshot to record an agent_step screenshot"
    )
    call = screenshots.record_calls[0]
    assert call.get("screenshot_type") == "agent_step"
    assert call.get("session_id"), "expected session_id on recorded screenshot"
    assert call.get("step") == 1
    assert call.get("url") == "https://example.com"
    assert call.get("has_error") is False

    metadata = call.get("metadata") or {}
    assert metadata.get("title") == "Example"
    assert metadata.get("source") == "browser_state_summary"


def test_c3_agent_step_per_session_cap_evicts_oldest() -> None:
    try:
        src = inspect.getsource(ScreenshotManager.record_screenshot)
    except Exception:  # noqa: BLE001
        src = ""
    if "agent_step" not in src:
        pytest.xfail("C3 per-session cap not implemented in ScreenshotManager yet")

    manager = ScreenshotManager(max_screenshots=1000)
    session_id = "session-a"
    for step in range(1, 61):
        manager.record_screenshot(
            screenshot_type="agent_step",
            image_bytes=b"img",
            mime_type="image/png",
            session_id=session_id,
            captured_at=float(step),
            metadata={"step": step},
            url="https://example.com",
            step=step,
        )

    shots = manager.get_screenshots(
        screenshot_type="agent_step", session_id=session_id, last_n=1000, include_images=False
    )
    assert len(shots) == 50
    assert [shot["step"] for shot in shots] == list(range(11, 61))


def test_a2_early_abort_guarantees_step_1_screenshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = _web_eval_agent_source()
    if "ensure_required_step_screenshots" not in src:
        pytest.xfail("A2 screenshot guarantee not implemented in this branch yet")

    screenshots = _DummyScreenshotManager()
    runtime = _DummyRuntime(screenshots=screenshots)

    class _EarlyAbortAgent(_DummyAgent):
        async def run(self, *args: Any, **kwargs: Any) -> _DummyHistory:
            info = _StepInfo(
                step=1,
                url="https://example.com",
                title="Example",
                screenshot=None,
            )
            if self._step_callback is not None:
                try:
                    result = self._step_callback(info, None, info.step)
                    if inspect.isawaitable(result):
                        await result
                except TypeError:
                    result = self._step_callback(info)
                    if inspect.isawaitable(result):
                        await result
            return _DummyHistory()

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: runtime)
    monkeypatch.setattr(mcp_server_mod, "load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        mcp_server_mod,
        "create_browser_use_llms",
        lambda *args, **kwargs: type("DummyLLMs", (), {"primary": object(), "fallback": None})(),
    )
    monkeypatch.setattr(
        mcp_server_mod,
        "_load_browser_use_classes",
        lambda: (_EarlyAbortAgent, _DummyBrowserSession),
    )

    _DummyAgent.created.clear()
    _DummyBrowserSession.created.clear()
    response = _run(
        mcp_server_mod.web_eval_agent(
            url="example.com",
            task="do something",
            ctx=object(),
            headless_browser=True,
        )
    )
    payload = _parse_payload(response)
    assert payload["status"] in ("success", "partial", "failed")

    assert screenshots.record_calls, "expected at least one screenshot to be recorded"
    step_1_shots = [call for call in screenshots.record_calls if call.get("step") == 1]
    assert step_1_shots, "expected step 1 screenshot to be guaranteed"

    call = step_1_shots[0]
    assert call.get("screenshot_type") == "agent_step"
    assert call.get("session_id"), "expected session_id on recorded screenshot"


def test_a2_early_abort_with_error_guarantees_screenshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = _web_eval_agent_source()
    if "ensure_required_step_screenshots" not in src:
        pytest.xfail("A2 screenshot guarantee not implemented in this branch yet")

    screenshots = _DummyScreenshotManager()
    runtime = _DummyRuntime(screenshots=screenshots)

    class _ErrorAgent(_DummyAgent):
        async def run(self, *args: Any, **kwargs: Any) -> _DummyHistory:
            raise RuntimeError("agent error")

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: runtime)
    monkeypatch.setattr(mcp_server_mod, "load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        mcp_server_mod,
        "create_browser_use_llms",
        lambda *args, **kwargs: type("DummyLLMs", (), {"primary": object(), "fallback": None})(),
    )
    monkeypatch.setattr(
        mcp_server_mod, "_load_browser_use_classes", lambda: (_ErrorAgent, _DummyBrowserSession)
    )

    _DummyAgent.created.clear()
    _DummyBrowserSession.created.clear()
    response = _run(
        mcp_server_mod.web_eval_agent(
            url="example.com",
            task="do something",
            ctx=object(),
            headless_browser=True,
        )
    )
    payload = _parse_payload(response)
    assert payload["status"] in ("success", "partial", "failed")

    assert screenshots.record_calls, "expected at least one screenshot despite error"


def test_a2_multi_step_no_screenshots_guarantees_step_1_and_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = _web_eval_agent_source()
    if "ensure_required_step_screenshots" not in src:
        pytest.xfail("A2 screenshot guarantee not implemented in this branch yet")

    screenshots = _DummyScreenshotManager()
    runtime = _DummyRuntime(screenshots=screenshots)

    class _MultiStepAgent(_DummyAgent):
        async def run(self, *args: Any, **kwargs: Any) -> _DummyHistory:
            for step in [1, 2, 3]:
                info = _StepInfo(
                    step=step,
                    url="https://example.com",
                    title=f"Example {step}",
                    screenshot=None,
                )
                if self._step_callback is not None:
                    try:
                        result = self._step_callback(info, None, info.step)
                        if inspect.isawaitable(result):
                            await result
                    except TypeError:
                        result = self._step_callback(info)
                        if inspect.isawaitable(result):
                            await result
            return _DummyHistory()

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: runtime)
    monkeypatch.setattr(mcp_server_mod, "load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        mcp_server_mod,
        "create_browser_use_llms",
        lambda *args, **kwargs: type("DummyLLMs", (), {"primary": object(), "fallback": None})(),
    )
    monkeypatch.setattr(
        mcp_server_mod, "_load_browser_use_classes", lambda: (_MultiStepAgent, _DummyBrowserSession)
    )

    _DummyAgent.created.clear()
    _DummyBrowserSession.created.clear()
    response = _run(
        mcp_server_mod.web_eval_agent(
            url="example.com",
            task="do something",
            ctx=object(),
            headless_browser=True,
        )
    )
    payload = _parse_payload(response)
    assert payload["status"] in ("success", "partial", "failed")

    assert screenshots.record_calls, "expected at least one screenshot to be recorded"

    step_1_shots = [call for call in screenshots.record_calls if call.get("step") == 1]
    assert step_1_shots, "expected step 1 screenshot to be guaranteed"

    step_3_shots = [call for call in screenshots.record_calls if call.get("step") == 3]
    assert step_3_shots, "expected final step (step 3) screenshot to be guaranteed"
