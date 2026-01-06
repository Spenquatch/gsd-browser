from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest

from gsd_browser import mcp_server as mcp_server_mod
from gsd_browser.run_event_store import RunEventStore


def _run(value: Any) -> Any:
    if asyncio.iscoroutine(value) or asyncio.isfuture(value):
        return asyncio.run(value)
    return value


def _parse_payload(response: list[Any]) -> dict[str, Any]:
    assert isinstance(response, list)
    assert len(response) == 1
    assert getattr(response[0], "type", None) == "text"
    payload = json.loads(getattr(response[0], "text", ""))
    assert isinstance(payload, dict)
    return payload


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


def _install_web_eval_agent_stubs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    agent_run_side_effect: Exception | None = None,
) -> None:
    monkeypatch.setattr(mcp_server_mod, "load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        mcp_server_mod,
        "create_browser_use_llms",
        lambda *args, **kwargs: type("DummyLLMs", (), {"primary": object(), "fallback": None})(),
    )

    class _DummyAgent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._step_callback = None

        def register_new_step_callback(self, callback: Any) -> None:
            self._step_callback = callback

        async def run(self, *args: Any, **kwargs: Any) -> Any:
            if agent_run_side_effect is not None:
                raise agent_run_side_effect
            # Should not reach here in error tests
            raise AssertionError("agent.run() should have raised an error")

    class _DummyBrowserSession:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.cdp_client = object()

    monkeypatch.setattr(
        mcp_server_mod, "_load_browser_use_classes", lambda: (_DummyAgent, _DummyBrowserSession)
    )


def test_a3_schema_validation_failure_emits_has_error_agent_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A3: Schema validation failure emits a has_error=true agent event."""
    session_uuid = uuid.UUID(int=2)
    session_id = str(session_uuid)
    store = RunEventStore()
    store.ensure_session(session_id, created_at=0.0)

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: _DummyRuntime(run_events=store))

    # Simulate a Pydantic ValidationError (schema validation failure)
    try:
        from pydantic import ValidationError as PydanticValidationError

        validation_error = PydanticValidationError.from_exception_data(
            "AgentOutput",
            [
                {
                    "type": "missing",
                    "loc": ("action",),
                    "msg": "Field required",
                    "input": {},
                }
            ],
        )
    except (ImportError, AttributeError):
        # Fallback if pydantic is not available or API changed
        validation_error = ValueError("Validation error: 'action' field required")

    _install_web_eval_agent_stubs(monkeypatch, agent_run_side_effect=validation_error)

    uuids = [uuid.UUID(int=1), session_uuid]

    def _uuid4() -> uuid.UUID:
        return uuids.pop(0)

    monkeypatch.setattr(mcp_server_mod.uuid, "uuid4", _uuid4)

    payload = _parse_payload(
        _run(
            mcp_server_mod.web_eval_agent(
                url="https://example.com",
                task="test task",
                ctx=object(),
                headless_browser=True,
                mode="compact",
            )
        )
    )

    assert payload["status"] == "failed"
    assert payload["session_id"] == session_id
    assert (
        "Validation" in str(payload.get("summary", ""))
        or "validation" in str(payload.get("summary", "")).lower()
    )

    # Query for agent events with has_error=true
    agent_error_events = store.get_events(
        session_id=session_id,
        event_types=["agent"],
        has_error=True,
        last_n=50,
        include_details=False,
    )

    assert len(agent_error_events) >= 1, (
        "Expected at least one agent error event for schema validation failure"
    )

    # Verify the event properties
    first_event = agent_error_events[0]
    assert first_event.get("event_type") == "agent"
    assert first_event.get("has_error") is True
    assert isinstance(first_event.get("summary"), str)


def test_a3_provider_error_emits_has_error_agent_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A3: Provider error emits a has_error=true agent event."""
    session_uuid = uuid.UUID(int=3)
    session_id = str(session_uuid)
    store = RunEventStore()
    store.ensure_session(session_id, created_at=0.0)

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: _DummyRuntime(run_events=store))

    # Simulate a ModelProviderError or similar provider-level failure
    class ModelProviderError(Exception):
        """Mock provider error."""

        pass

    provider_error = ModelProviderError("Rate limit exceeded")

    _install_web_eval_agent_stubs(monkeypatch, agent_run_side_effect=provider_error)

    uuids = [uuid.UUID(int=1), session_uuid]

    def _uuid4() -> uuid.UUID:
        return uuids.pop(0)

    monkeypatch.setattr(mcp_server_mod.uuid, "uuid4", _uuid4)

    payload = _parse_payload(
        _run(
            mcp_server_mod.web_eval_agent(
                url="https://example.com",
                task="test task",
                ctx=object(),
                headless_browser=True,
                mode="compact",
            )
        )
    )

    assert payload["status"] == "failed"
    assert payload["session_id"] == session_id
    assert "ModelProviderError" in str(payload.get("summary", "")) or "Rate limit" in str(
        payload.get("summary", "")
    )

    # Query for agent events with has_error=true
    agent_error_events = store.get_events(
        session_id=session_id,
        event_types=["agent"],
        has_error=True,
        last_n=50,
        include_details=False,
    )

    assert len(agent_error_events) >= 1, (
        "Expected at least one agent error event for provider error"
    )

    # Verify the event properties
    first_event = agent_error_events[0]
    assert first_event.get("event_type") == "agent"
    assert first_event.get("has_error") is True
    assert isinstance(first_event.get("summary"), str)
