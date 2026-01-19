from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from typing import Any

import pytest

from gsd_browser import mcp_server as mcp_server_mod
from gsd_browser.contracts.v1 import GetScreenshotsPayloadV1, SetupBrowserStatePayloadV1


def _run(value: Any) -> Any:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


class _DummyRuntime:
    def __init__(self, *, screenshots: Any | None = None) -> None:
        self.screenshots = screenshots

    def ensure_dashboard_running(self, *args: Any, **kwargs: Any) -> None:
        return None


def test_setup_browser_state_returns_versioned_json(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _capture_state_interactive(*args: Any, **kwargs: Any) -> str:
        return "/tmp/state.json"

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: _DummyRuntime())
    monkeypatch.setattr(mcp_server_mod, "load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr(mcp_server_mod, "capture_state_interactive", _capture_state_interactive)

    result = _run(mcp_server_mod.setup_browser_state(url="https://example.com", state_id="github"))
    assert isinstance(result, list)
    assert len(result) == 1
    assert getattr(result[0], "type", None) == "text"

    payload = json.loads(getattr(result[0], "text", ""))
    SetupBrowserStatePayloadV1.model_validate(payload)
    assert payload["version"] == "gsd.setup_browser_state.v1"
    assert payload["status"] == "success"
    assert payload["state_id"] == "github"
    assert payload["path"]
    assert isinstance(payload["next_actions"], list)


def test_get_screenshots_emits_versioned_json_header(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = str(uuid.uuid4())
    shot_id = str(uuid.uuid4())

    class _DummyScreenshots:
        def get_screenshots(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            return [
                {
                    "id": shot_id,
                    "timestamp": 123.0,
                    "type": "agent_step",
                    "session_id": kwargs.get("session_id"),
                    "has_error": False,
                    "mime_type": "image/png",
                    "url": "https://example.com",
                    "step": 1,
                    "metadata": {"k": "v"},
                    "image_data": "aGVsbG8=",  # "hello" base64 (not a real png; unit test only)
                }
            ]

        def get_stats(self) -> dict[str, Any]:
            return {"total_screenshots": 1, "sampling_rate": 10}

    monkeypatch.setattr(
        mcp_server_mod,
        "get_runtime",
        lambda: _DummyRuntime(screenshots=_DummyScreenshots()),
    )

    result = _run(
        mcp_server_mod.get_screenshots(session_id=session_id, last_n=5, include_images=False)
    )
    assert isinstance(result, list)
    assert len(result) == 1
    assert getattr(result[0], "type", None) == "text"

    payload = json.loads(getattr(result[0], "text", ""))
    GetScreenshotsPayloadV1.model_validate(payload)
    assert payload["version"] == "gsd.get_screenshots.v1"
    assert isinstance(payload["screenshots"], list)
    artifact = payload["screenshots"][0]["artifact"]
    assert str(artifact["key"]) == shot_id
    assert artifact["url"] is None
    assert artifact["content_type"] == "image/png"
    assert artifact["created_at"] == 123.0
