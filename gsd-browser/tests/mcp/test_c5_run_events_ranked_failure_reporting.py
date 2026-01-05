from __future__ import annotations

import asyncio
import base64
import inspect
import json
import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from gsd_browser import mcp_server as mcp_server_mod
from gsd_browser.run_event_store import RunEventStore


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


def test_c5_run_event_store_helpers_enforce_bounds_and_truncate() -> None:
    store = RunEventStore(max_events_per_session_type=2, max_len=12)
    session_id = "s-1"
    store.ensure_session(session_id, created_at=0.0)

    long_message = "x" * 100
    long_url = "https://example.com/" + ("y" * 100)

    for idx in range(5):
        store.record_console_event(
            session_id,
            captured_at=float(idx),
            level="error",
            message=long_message,
            location={"url": long_url, "line": idx, "column": 1, "function": "handler"},
        )

    console_events = store.get_events(
        session_id=session_id,
        event_types=["console"],
        last_n=10,
        include_details=True,
    )
    assert len(console_events) == 2
    assert all(event.get("event_type") == "console" for event in console_events)
    assert all(event.get("has_error") is True for event in console_events)

    for event in console_events:
        summary = str(event.get("summary") or "")
        assert summary.endswith("…")
        assert len(summary) == 12
        details = event.get("details") or {}
        assert details.get("level") == "error"
        location = (details.get("location") or {}) if isinstance(details, dict) else {}
        if isinstance(location, dict) and location.get("url"):
            location_url = str(location["url"])
            assert location_url.endswith("…")
            assert len(location_url) == 12

    for idx in range(5):
        store.record_network_event(
            session_id,
            captured_at=10.0 + idx,
            method="GET",
            url=long_url,
            status=500,
            error="net::ERR_BLOCKED_BY_CLIENT" if idx == 0 else None,
        )

    network_events = store.get_events(
        session_id=session_id,
        event_types=["network"],
        last_n=10,
        include_details=True,
    )
    assert len(network_events) == 2
    assert all(event.get("event_type") == "network" for event in network_events)
    assert all(event.get("has_error") is True for event in network_events)

    for event in network_events:
        summary = str(event.get("summary") or "")
        assert summary.endswith("…")
        assert len(summary) == 12
        details = event.get("details") or {}
        assert isinstance(details, dict)
        assert str(details.get("url") or "").endswith("…")
        assert len(str(details.get("url") or "")) == 12


@dataclass
class _StepInfo:
    step: int
    url: str
    title: str
    screenshot: str

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


class _DummyRuntime:
    def __init__(self, *, run_events: RunEventStore) -> None:
        self.run_events = run_events

        class _DummyScreenshots:
            current_session_id: str | None = None
            current_session_start: float | None = None

            def record_screenshot(self, **_: Any) -> None:  # type: ignore[no-untyped-def]
                return None

        self.screenshots = _DummyScreenshots()

    def ensure_dashboard_running(self, *args: Any, **kwargs: Any) -> None:
        return None


def _install_web_eval_agent_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server_mod, "load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        mcp_server_mod,
        "create_browser_use_llms",
        lambda *args, **kwargs: type("DummyLLMs", (), {"primary": object(), "fallback": None})(),
    )

    class _DummyHistory:
        history: list[object] = []

        def final_result(self) -> str | None:
            return None

        def has_errors(self) -> bool:
            return True

        def errors(self) -> list[object]:
            return ["boom"]

    class _DummyAgent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._step_callback = None

        def register_new_step_callback(self, callback: Any) -> None:
            self._step_callback = callback

        async def run(self, *args: Any, **kwargs: Any) -> _DummyHistory:
            if callable(self._step_callback):
                info = _StepInfo(
                    step=2,
                    url="https://primary.example/login",
                    title="Login",
                    screenshot=base64.b64encode(b"img").decode("ascii"),
                )
                result = self._step_callback(info, None, info.step)
                if inspect.isawaitable(result):
                    await result
            return _DummyHistory()

    class _DummyBrowserSession:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.cdp_client = object()

    monkeypatch.setattr(
        mcp_server_mod, "_load_browser_use_classes", lambda: (_DummyAgent, _DummyBrowserSession)
    )


def test_c5_web_eval_agent_failure_payload_includes_failure_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_uuid = uuid.UUID(int=2)
    store = RunEventStore()
    store.ensure_session(str(session_uuid), created_at=0.0)

    store.record_network_event(
        str(session_uuid),
        captured_at=1.0,
        method="GET",
        url="https://primary.example/api/login",
        status=500,
        error=None,
    )

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: _DummyRuntime(run_events=store))
    _install_web_eval_agent_stubs(monkeypatch)

    uuids = [uuid.UUID(int=1), session_uuid]

    def _uuid4() -> uuid.UUID:
        return uuids.pop(0)

    monkeypatch.setattr(mcp_server_mod.uuid, "uuid4", _uuid4)

    payload = _parse_payload(
        _run(
            mcp_server_mod.web_eval_agent(
                url="https://primary.example",
                task="fail",
                ctx=object(),
                headless_browser=True,
                mode="compact",
            )
        )
    )
    assert payload["status"] == "failed"
    assert payload["session_id"] == str(session_uuid)

    assert isinstance(payload.get("next_actions"), list)
    assert any("get_run_events" in str(item) for item in payload["next_actions"])

    page = payload.get("page")
    assert isinstance(page, dict)
    assert page.get("url") == "https://primary.example/login"
    assert page.get("title") == "Login"

    errors_top = payload.get("errors_top")
    assert isinstance(errors_top, list)
    assert errors_top, "expected at least one ranked error summary"
    for entry in errors_top:
        assert isinstance(entry, dict)
        assert entry.get("type") in {"console", "network", "agent", "judge"}
        assert isinstance(entry.get("summary"), str)
        assert "step" in entry
        assert "url" in entry


def test_c5_ranked_errors_downrank_blocked_by_client(monkeypatch: pytest.MonkeyPatch) -> None:
    session_uuid = uuid.UUID(int=2)
    session_id = str(session_uuid)
    store = RunEventStore()
    store.ensure_session(session_id, created_at=0.0)

    store.record_network_event(
        session_id,
        captured_at=1.0,
        method="GET",
        url="https://telemetry.example/collect",
        status=503,
        error=None,
    )
    store.record_network_event(
        session_id,
        captured_at=2.0,
        method="GET",
        url="https://ads.example/script.js",
        status=None,
        error="net::ERR_BLOCKED_BY_CLIENT",
    )
    store.record_network_event(
        session_id,
        captured_at=3.0,
        method="POST",
        url="https://primary.example/api/login",
        status=500,
        error=None,
    )

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: _DummyRuntime(run_events=store))
    _install_web_eval_agent_stubs(monkeypatch)

    uuids = [uuid.UUID(int=1), session_uuid]

    def _uuid4() -> uuid.UUID:
        return uuids.pop(0)

    monkeypatch.setattr(mcp_server_mod.uuid, "uuid4", _uuid4)

    payload = _parse_payload(
        _run(
            mcp_server_mod.web_eval_agent(
                url="https://primary.example",
                task="fail",
                ctx=object(),
                headless_browser=True,
                mode="compact",
            )
        )
    )

    errors_top = payload.get("errors_top")
    assert isinstance(errors_top, list)

    primary_idx = next(
        (
            idx
            for idx, entry in enumerate(errors_top)
            if entry.get("type") == "network"
            and "primary.example/api/login" in str(entry.get("url") or "")
        ),
        None,
    )
    assert primary_idx is not None, "expected primary-origin 500 to surface in errors_top"

    blocked_idx = next(
        (
            idx
            for idx, entry in enumerate(errors_top)
            if "ads.example" in str(entry.get("url") or "")
            or "BLOCKED_BY_CLIENT" in str(entry.get("summary") or "")
        ),
        None,
    )
    if blocked_idx is not None:
        assert blocked_idx > primary_idx
