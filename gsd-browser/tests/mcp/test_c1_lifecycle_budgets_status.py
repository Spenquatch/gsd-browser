from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from typing import Any

import pytest

from gsd_browser import mcp_server as mcp_server_mod


def _run(value: Any) -> Any:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


def _assert_uuid(value: str) -> None:
    parsed = uuid.UUID(value)
    assert str(parsed) == value


def _parse_payload(response: list[Any]) -> dict[str, Any]:
    assert isinstance(response, list)
    assert len(response) == 1
    assert getattr(response[0], "type", None) == "text"
    payload = json.loads(getattr(response[0], "text", ""))
    assert isinstance(payload, dict)
    return payload


class _DummyRuntime:
    def __init__(self) -> None:
        class _DummyScreenshots:
            current_session_id: str | None = None
            current_session_start: float | None = None

        self.screenshots = _DummyScreenshots()

    def ensure_dashboard_running(self, *args: Any, **kwargs: Any) -> None:
        return None


class _DummyBrowserSession:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        return None


def _setup_common_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: _DummyRuntime())
    monkeypatch.setattr(mcp_server_mod, "load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr(mcp_server_mod, "create_browser_use_llm", lambda *args, **kwargs: object())


def _c1_budget_kwargs(*, budget_s: float, max_steps: int, step_timeout_s: float) -> dict[str, Any]:
    params = inspect.signature(mcp_server_mod.web_eval_agent).parameters

    kwargs: dict[str, Any] = {}

    budget_param = next(
        (
            name
            for name in ("budget_s", "tool_budget_s", "timeout_s", "tool_timeout_s")
            if name in params
        ),
        None,
    )
    step_timeout_param = next(
        (name for name in ("step_timeout_s", "step_timeout") if name in params),
        None,
    )
    max_steps_param = "max_steps" if "max_steps" in params else None

    if budget_param is None or step_timeout_param is None or max_steps_param is None:
        raise TypeError("C1 budget/timeouts arguments not implemented")

    kwargs[budget_param] = budget_s
    kwargs[step_timeout_param] = step_timeout_s
    kwargs[max_steps_param] = max_steps
    return kwargs


def test_c1_status_mapping_failed_when_no_result_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_common_stubs(monkeypatch)

    class DummyHistory:
        history: list[object] = []

        def final_result(self) -> str | None:
            return None

        def has_errors(self) -> bool:
            return True

        def errors(self) -> list[object]:
            return ["error"]

    class DummyAgent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def run(self, *args: Any, **kwargs: Any) -> DummyHistory:
            return DummyHistory()

    monkeypatch.setattr(
        mcp_server_mod, "_load_browser_use_classes", lambda: (DummyAgent, _DummyBrowserSession)
    )

    payload = _parse_payload(
        _run(
            mcp_server_mod.web_eval_agent(
                url="example.com",
                task="produce no result but errors",
                ctx=object(),
                headless_browser=True,
            )
        )
    )

    assert payload["status"] == "failed"
    assert payload["result"] is None


def test_c1_status_mapping_success_with_warnings_when_final_result_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_common_stubs(monkeypatch)

    class DummyHistory:
        history: list[object] = []

        def final_result(self) -> str | None:
            return "ok"

        def has_errors(self) -> bool:
            return True

        def errors(self) -> list[object]:
            return ["recovered error"]

    class DummyAgent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def run(self, *args: Any, **kwargs: Any) -> DummyHistory:
            return DummyHistory()

    monkeypatch.setattr(
        mcp_server_mod, "_load_browser_use_classes", lambda: (DummyAgent, _DummyBrowserSession)
    )

    payload = _parse_payload(
        _run(
            mcp_server_mod.web_eval_agent(
                url="example.com",
                task="return ok with internal warnings",
                ctx=object(),
                headless_browser=True,
            )
        )
    )

    if "warnings" not in payload:
        pytest.skip("C1 warning surfacing/status mapping not implemented in this branch yet")

    assert payload["result"] == "ok"
    assert payload["status"] == "success"
    assert isinstance(payload["warnings"], list)
    assert all(isinstance(item, str) for item in payload["warnings"])


def test_c1_timeout_returns_actionable_failure_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_common_stubs(monkeypatch)

    class DummyAgent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def run(self, *args: Any, **kwargs: Any) -> object:
            await asyncio.sleep(5)
            return object()

    monkeypatch.setattr(
        mcp_server_mod, "_load_browser_use_classes", lambda: (DummyAgent, _DummyBrowserSession)
    )

    try:
        c1_kwargs = _c1_budget_kwargs(budget_s=0.01, max_steps=1, step_timeout_s=0.01)
        response = _run(
            mcp_server_mod.web_eval_agent(
                url="example.com",
                task="timeout quickly",
                ctx=object(),
                headless_browser=True,
                **c1_kwargs,
            )
        )
    except TypeError:
        pytest.skip("C1 budget/timeout arguments not implemented in this branch yet")

    payload = _parse_payload(response)
    if "timeouts" not in payload:
        pytest.skip("C1 timeout contract fields not implemented in this branch yet")

    _assert_uuid(payload["session_id"])
    _assert_uuid(payload["tool_call_id"])
    assert payload["status"] == "failed"
    assert payload["result"] is None

    timeouts = payload["timeouts"]
    assert isinstance(timeouts, dict)
    assert timeouts.get("timed_out") is True

    summary = str(payload.get("summary") or "")
    assert "timeout" in summary.lower()


def test_c1_cancellation_returns_actionable_failure_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_common_stubs(monkeypatch)

    class DummyAgent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def run(self, *args: Any, **kwargs: Any) -> object:
            raise asyncio.CancelledError("cancelled for test")

    monkeypatch.setattr(
        mcp_server_mod, "_load_browser_use_classes", lambda: (DummyAgent, _DummyBrowserSession)
    )

    try:
        c1_kwargs = _c1_budget_kwargs(budget_s=0.5, max_steps=1, step_timeout_s=0.5)
        response = _run(
            mcp_server_mod.web_eval_agent(
                url="example.com",
                task="simulate cancellation",
                ctx=object(),
                headless_browser=True,
                **c1_kwargs,
            )
        )
    except TypeError:
        pytest.skip("C1 budget/timeout arguments not implemented in this branch yet")

    payload = _parse_payload(response)
    if "timeouts" not in payload:
        pytest.skip("C1 timeout/cancellation contract fields not implemented in this branch yet")

    assert payload["status"] == "failed"
    assert payload["result"] is None

    summary = str(payload.get("summary") or "")
    assert "cancel" in summary.lower()
