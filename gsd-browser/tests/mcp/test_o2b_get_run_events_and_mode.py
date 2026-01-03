from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any

import pytest

from gsd_browser import mcp_server as mcp_server_mod
from gsd_browser.run_event_store import RunEventStore


def _run(value: Any) -> Any:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


def _parse_single_text_payload(response: list[Any]) -> dict[str, Any]:
    assert isinstance(response, list)
    assert len(response) == 1
    assert getattr(response[0], "type", None) == "text"
    payload = getattr(response[0], "text", "")
    return json.loads(payload)


def _o2b_get_run_events_tool_present() -> bool:
    module_src = inspect.getsource(mcp_server_mod)
    return (
        "gsd-browser.get_run_events.v1" in module_src
        or 'name="get_run_events"' in module_src
        or "name='get_run_events'" in module_src
    )


def _o2b_mode_arg_present() -> bool:
    signature = inspect.signature(mcp_server_mod.web_eval_agent)
    return "mode" in signature.parameters


class _DummyRuntime:
    def __init__(self, *, run_events: RunEventStore) -> None:
        self.run_events = run_events

    def ensure_dashboard_running(self, *args: Any, **kwargs: Any) -> None:
        return None


def _install_web_eval_agent_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server_mod, "load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr(mcp_server_mod, "create_browser_use_llm", lambda *args, **kwargs: object())

    class _DummyHistory:
        history: list[object] = []

        def final_result(self) -> str | None:
            return "ok"

        def has_errors(self) -> bool:
            return False

        def errors(self) -> list[object]:
            return []

    class _DummyAgent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        def register_new_step_callback(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def run(self, *args: Any, **kwargs: Any) -> _DummyHistory:
            return _DummyHistory()

    class _DummyBrowserSession:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

    monkeypatch.setattr(
        mcp_server_mod, "_load_browser_use_classes", lambda: (_DummyAgent, _DummyBrowserSession)
    )


def test_o2b_get_run_events_enforces_limits_and_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    if not _o2b_get_run_events_tool_present():
        pytest.skip("O2b get_run_events tool not implemented in this branch yet")

    get_run_events = getattr(mcp_server_mod, "get_run_events", None)
    if not callable(get_run_events):
        pytest.skip("O2b get_run_events tool not available as a callable")

    store = RunEventStore()
    session_id = "s-1"
    store.ensure_session(session_id, created_at=0.0)

    for idx in range(300):
        store.record_event(
            session_id=session_id,
            event_type="network",
            timestamp=float(idx),
            summary=f"GET /resource/{idx}",
            details={"status": 200 if idx % 2 == 0 else 500},
            has_error=idx % 2 == 1,
        )

    store.record_event(
        session_id=session_id,
        event_type="console",
        timestamp=999.0,
        summary="console boom",
        details={"level": "error", "location": {"url": "https://example.com", "line": 1}},
        has_error=True,
    )

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: _DummyRuntime(run_events=store))

    payload = _parse_single_text_payload(_run(get_run_events(session_id=session_id)))
    assert payload["version"] == "gsd-browser.get_run_events.v1"
    assert payload["session_id"] == session_id
    assert isinstance(payload.get("events"), list)
    assert len(payload["events"]) == 50
    assert isinstance(payload.get("stats"), dict)

    assert all("details" not in item for item in payload["events"])

    payload = _parse_single_text_payload(_run(get_run_events(session_id=session_id, last_n=999)))
    assert len(payload["events"]) == 200

    payload = _parse_single_text_payload(
        _run(get_run_events(session_id=session_id, event_types=["console"], last_n=200))
    )
    assert len(payload["events"]) == 1
    assert payload["events"][0].get("event_type") == "console"
    assert payload["events"][0].get("has_error") is True

    payload = _parse_single_text_payload(
        _run(get_run_events(session_id=session_id, from_timestamp=250.0, last_n=200))
    )
    assert all(float(item.get("timestamp", 0.0)) >= 250.0 for item in payload["events"])

    payload = _parse_single_text_payload(
        _run(get_run_events(session_id=session_id, has_error=False, last_n=200))
    )
    assert payload["events"]
    assert all(item.get("has_error") is False for item in payload["events"])

    payload = _parse_single_text_payload(
        _run(get_run_events(session_id=session_id, include_details=True, last_n=5))
    )
    assert payload["events"]
    assert any("details" in item for item in payload["events"])


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://localhost:3000", "dev"),
        ("http://127.0.0.1:5173", "dev"),
        ("https://example.com", "compact"),
        ("example.com", "compact"),
    ],
)
def test_o2b_web_eval_agent_mode_defaults_based_on_host(
    monkeypatch: pytest.MonkeyPatch, url: str, expected: str
) -> None:
    if not _o2b_mode_arg_present():
        pytest.skip("O2b web_eval_agent mode selection not implemented in this branch yet")

    store = RunEventStore()
    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: _DummyRuntime(run_events=store))
    _install_web_eval_agent_stubs(monkeypatch)

    payload = _parse_single_text_payload(
        _run(
            mcp_server_mod.web_eval_agent(
                url=url,
                task="return a short answer",
                ctx=object(),
                headless_browser=True,
            )
        )
    )
    assert payload["mode"] == expected


def test_o2b_web_eval_agent_mode_explicit_override(monkeypatch: pytest.MonkeyPatch) -> None:
    if not _o2b_mode_arg_present():
        pytest.skip("O2b web_eval_agent mode selection not implemented in this branch yet")

    store = RunEventStore()
    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: _DummyRuntime(run_events=store))
    _install_web_eval_agent_stubs(monkeypatch)

    payload = _parse_single_text_payload(
        _run(
            mcp_server_mod.web_eval_agent(
                url="http://localhost:3000",
                task="return a short answer",
                mode="compact",
                ctx=object(),
                headless_browser=True,
            )
        )
    )
    assert payload["mode"] == "compact"

    payload = _parse_single_text_payload(
        _run(
            mcp_server_mod.web_eval_agent(
                url="https://example.com",
                task="return a short answer",
                mode="dev",
                ctx=object(),
                headless_browser=True,
            )
        )
    )
    assert payload["mode"] == "dev"
