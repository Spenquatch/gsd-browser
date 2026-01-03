from __future__ import annotations

import asyncio
import json
import importlib
import inspect
from collections.abc import Callable
from typing import Any

import pytest

from gsd_browser import mcp_server as mcp_server_mod


def _load_run_event_store_class() -> type[Any] | None:
    for module_name in (
        "gsd_browser.run_event_store",
        "gsd_browser.run_events",
        "gsd_browser.events",
    ):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        store_cls = getattr(module, "RunEventStore", None)
        if isinstance(store_cls, type):
            return store_cls
    return None


def _make_store(
    store_cls: type[Any],
) -> tuple[Any, int | None, int | None]:
    candidates: list[tuple[int | None, int | None, dict[str, Any]]] = [
        (3, 12, {"max_events_per_session_type": 3, "max_string_length": 12}),
        (3, 12, {"max_events_per_session_type": 3, "max_field_length": 12}),
        (3, 12, {"max_events_per_session_type": 3, "max_len": 12}),
        (3, 12, {"max_events_per_type": 3, "max_string_length": 12}),
        (3, 12, {"max_events_per_type": 3, "max_field_length": 12}),
        (3, 12, {"max_events_per_type": 3, "max_len": 12}),
        (3, 12, {"max_events": 3, "max_string_length": 12}),
        (3, 12, {"max_events": 3, "max_field_length": 12}),
        (3, 12, {"max_events": 3, "max_len": 12}),
        (None, 12, {"max_string_length": 12}),
        (None, 12, {"max_field_length": 12}),
        (None, 12, {"max_len": 12}),
        (None, None, {}),
    ]

    last_exc: Exception | None = None
    for max_events, max_string_length, kwargs in candidates:
        try:
            return store_cls(**kwargs), max_events, max_string_length
        except TypeError as exc:
            last_exc = exc
            continue

    raise AssertionError(f"Unable to construct {store_cls}: {last_exc}")


def _find_callable(target: Any, names: tuple[str, ...]) -> Callable[..., Any] | None:
    for name in names:
        candidate = getattr(target, name, None)
        if callable(candidate):
            return candidate
    return None


def _record_event(
    store: Any,
    *,
    session_id: str,
    event_type: str,
    timestamp: float,
    summary: str,
    details: dict[str, Any] | None = None,
    has_error: bool = False,
) -> Any:
    record_fn = _find_callable(store, ("record_event", "add_event", "record_run_event"))
    if record_fn is None:
        pytest.skip("RunEventStore record method not implemented yet")

    kwargs: dict[str, Any] = {
        "session_id": session_id,
        "event_type": event_type,
        "timestamp": timestamp,
        "summary": summary,
        "details": details,
        "has_error": has_error,
    }
    signature = inspect.signature(record_fn)
    accepted = {key: value for key, value in kwargs.items() if key in signature.parameters}
    if not accepted:
        pytest.skip("RunEventStore record method signature not compatible with expected kwargs")
    return record_fn(**accepted)


def _get_events(
    store: Any,
    *,
    session_id: str | None = None,
    last_n: int = 50,
    event_types: list[str] | None = None,
    from_timestamp: float | None = None,
    has_error: bool | None = None,
    include_details: bool = False,
) -> list[Any]:
    query_fn = _find_callable(
        store, ("get_events", "get_run_events", "query_events", "list_events")
    )
    if query_fn is None:
        pytest.skip("RunEventStore query method not implemented yet")

    kwargs: dict[str, Any] = {
        "session_id": session_id,
        "last_n": last_n,
        "event_types": event_types,
        "from_timestamp": from_timestamp,
        "has_error": has_error,
        "include_details": include_details,
    }
    signature = inspect.signature(query_fn)
    accepted = {key: value for key, value in kwargs.items() if key in signature.parameters}
    if "last_n" not in accepted:
        accepted.pop("last_n", None)
    result = query_fn(**accepted)
    assert isinstance(result, list)
    return result


def _event_field(event: Any, key: str) -> Any:
    if isinstance(event, dict):
        return event.get(key)
    return getattr(event, key, None)


def _event_type(event: Any) -> str | None:
    return _event_field(event, "event_type") or _event_field(event, "type")


def _event_has_error(event: Any) -> bool | None:
    value = _event_field(event, "has_error")
    if value is None:
        return None
    return bool(value)


def _event_summary(event: Any) -> str | None:
    value = _event_field(event, "summary")
    if value is None:
        return None
    return str(value)


def _event_details(event: Any) -> Any:
    if isinstance(event, dict):
        return event.get("details")
    return getattr(event, "details", None)


def _o2a_mcp_integration_present() -> bool:
    module_src = inspect.getsource(mcp_server_mod)
    return (
        "run_event_store" in module_src
        or "RunEventStore" in module_src
        or "run_events." in module_src
        or "record_event(" in module_src
    )


def test_o2a_event_store_enforces_per_session_per_type_caps() -> None:
    store_cls = _load_run_event_store_class()
    if store_cls is None:
        pytest.skip("O2a run event store not implemented in this branch yet")

    store, expected_max_events, _ = _make_store(store_cls)
    if expected_max_events is None:
        pytest.skip("RunEventStore does not expose a configurable max events limit for testing")

    session_id = "s-1"
    for idx in range(10):
        _record_event(
            store,
            session_id=session_id,
            event_type="agent",
            timestamp=float(idx),
            summary=f"step={idx}",
            details={"step": idx},
        )

    events = _get_events(store, session_id=session_id, event_types=["agent"], last_n=100)
    assert len(events) == expected_max_events
    assert all(_event_type(item) == "agent" for item in events)


def test_o2a_event_store_truncates_string_fields_with_indicator() -> None:
    store_cls = _load_run_event_store_class()
    if store_cls is None:
        pytest.skip("O2a run event store not implemented in this branch yet")

    store, _, expected_max_len = _make_store(store_cls)
    if expected_max_len is None:
        pytest.skip("RunEventStore does not expose a configurable max string length for testing")

    long_text = "x" * (expected_max_len + 25)
    _record_event(
        store,
        session_id="s-1",
        event_type="console",
        timestamp=1.0,
        summary=long_text,
        details={"message": long_text},
        has_error=True,
    )

    events = _get_events(
        store, session_id="s-1", event_types=["console"], last_n=10, include_details=True
    )
    assert len(events) == 1
    summary = _event_summary(events[0])
    assert summary is not None
    assert summary.endswith("…")
    assert len(summary) == expected_max_len

    details = _event_details(events[0])
    if isinstance(details, dict) and "message" in details and isinstance(details["message"], str):
        assert details["message"].endswith("…")
        assert len(details["message"]) == expected_max_len


def test_o2a_event_store_filters_by_session_type_time_and_error() -> None:
    store_cls = _load_run_event_store_class()
    if store_cls is None:
        pytest.skip("O2a run event store not implemented in this branch yet")

    store, _, _ = _make_store(store_cls)

    _record_event(
        store,
        session_id="s-1",
        event_type="network",
        timestamp=1.0,
        summary="GET /ok",
        details={"status": 200},
        has_error=False,
    )
    _record_event(
        store,
        session_id="s-1",
        event_type="network",
        timestamp=2.0,
        summary="GET /fail",
        details={"status": 500},
        has_error=True,
    )
    _record_event(
        store,
        session_id="s-2",
        event_type="network",
        timestamp=3.0,
        summary="GET /other",
        details={"status": 404},
        has_error=True,
    )

    events = _get_events(
        store,
        session_id="s-1",
        event_types=["network"],
        from_timestamp=1.5,
        has_error=True,
        include_details=False,
    )
    assert len(events) == 1
    assert _event_type(events[0]) == "network"
    assert _event_has_error(events[0]) is True
    assert _event_details(events[0]) in (None, {})


def test_o2a_web_eval_agent_updates_run_event_artifact_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not _o2a_mcp_integration_present():
        pytest.skip("O2a MCP integration not implemented in this branch yet")

    store_cls = _load_run_event_store_class()
    if store_cls is None:
        pytest.skip("O2a run event store not implemented in this branch yet")

    store, _, _ = _make_store(store_cls)

    def _parse_payload(response: list[Any]) -> dict[str, Any]:
        assert isinstance(response, list)
        assert len(response) == 1
        assert getattr(response[0], "type", None) == "text"
        payload = getattr(response[0], "text", "")
        return json.loads(payload)

    class _DummyRuntime:
        def __init__(self) -> None:
            class _DummyScreenshots:
                current_session_id: str | None = None
                current_session_start: float | None = None

                def record_screenshot(self, **_: Any) -> None:  # type: ignore[no-untyped-def]
                    return None

            self.screenshots = _DummyScreenshots()
            self.run_events = store

        def ensure_dashboard_running(self, *args: Any, **kwargs: Any) -> None:
            return None

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: _DummyRuntime())
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

    class _StepInfo:
        def __init__(self, *, step: int, url: str) -> None:
            self.step = step
            self.url = url

        def __getitem__(self, key: str) -> Any:
            return getattr(self, key)

    class _DummyAgent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._step_callback: Callable[..., Any] | None = None

        def register_new_step_callback(self, callback: Callable[..., Any]) -> None:
            self._step_callback = callback

        async def run(self, *args: Any, **kwargs: Any) -> _DummyHistory:
            if self._step_callback is not None:
                await self._step_callback(_StepInfo(step=1, url="https://example.com"), None, 1)
                await self._step_callback(_StepInfo(step=2, url="https://example.com"), None, 2)
            return _DummyHistory()

    class _DummyBrowserSession:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

    monkeypatch.setattr(
        mcp_server_mod, "_load_browser_use_classes", lambda: (_DummyAgent, _DummyBrowserSession)
    )

    response = asyncio.run(
        mcp_server_mod.web_eval_agent(
            url="example.com",
            task="do something",
            ctx=object(),
            headless_browser=True,
        )
    )
    payload = _parse_payload(response)
    session_id = str(payload.get("session_id") or "")

    artifacts = payload.get("artifacts") or {}
    assert isinstance(artifacts, dict)
    assert int(artifacts.get("run_events", 0)) >= 0

    events = _get_events(store, session_id=session_id, last_n=200, include_details=False)
    assert int(artifacts.get("run_events", 0)) == len(events)
