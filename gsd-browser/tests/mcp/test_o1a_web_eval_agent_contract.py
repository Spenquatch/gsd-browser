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


def _o1a_contract_present() -> bool:
    module_src = inspect.getsource(mcp_server_mod)
    return "gsd-browser.web_eval_agent.v1" in module_src


def _assert_uuid(value: str) -> None:
    parsed = uuid.UUID(value)
    assert str(parsed) == value


class _DummyRuntime:
    def __init__(self) -> None:
        self.screenshots = object()

    def ensure_dashboard_running(self, *args: Any, **kwargs: Any) -> None:
        return None


@pytest.mark.parametrize(
    ("final_result_value", "expected_result_value"),
    [
        ("hello world", "hello world"),
        (None, None),
    ],
)
def test_o1a_web_eval_agent_json_shape_and_final_result_mapping(
    monkeypatch: pytest.MonkeyPatch,
    final_result_value: str | None,
    expected_result_value: str | None,
) -> None:
    if not _o1a_contract_present():
        pytest.skip("O1a JSON response contract not implemented in this branch yet")

    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: _DummyRuntime())
    monkeypatch.setattr(mcp_server_mod, "load_settings", lambda *args, **kwargs: object())

    class DummyHistory:
        def final_result(self) -> str | None:
            return final_result_value

    class DummyAgent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def run(self, *args: Any, **kwargs: Any) -> DummyHistory:
            return DummyHistory()

    if hasattr(mcp_server_mod, "Agent"):
        monkeypatch.setattr(mcp_server_mod, "Agent", DummyAgent)
    elif hasattr(mcp_server_mod, "browser_use") and hasattr(mcp_server_mod.browser_use, "Agent"):
        monkeypatch.setattr(mcp_server_mod.browser_use, "Agent", DummyAgent)
    else:
        pytest.skip("Unable to stub browser-use Agent in current module structure")

    response = _run(
        mcp_server_mod.web_eval_agent(
            url="example.com",
            task="return a short answer",
            ctx=object(),  # Context is not required for this unit test
            headless_browser=True,
        )
    )

    assert isinstance(response, list)
    assert len(response) == 1
    assert getattr(response[0], "type", None) == "text"
    assert all(getattr(item, "type", None) != "image" for item in response)

    json_text = getattr(response[0], "text", "")
    payload = json.loads(json_text)

    required_keys = {
        "version",
        "session_id",
        "tool_call_id",
        "url",
        "task",
        "mode",
        "status",
        "result",
        "summary",
        "artifacts",
        "next_actions",
    }
    assert required_keys.issubset(payload.keys())

    assert payload["version"] == "gsd-browser.web_eval_agent.v1"
    _assert_uuid(payload["session_id"])
    _assert_uuid(payload["tool_call_id"])

    assert payload["url"].startswith("https://")
    assert payload["task"] == "return a short answer"

    assert payload["mode"] in ("compact", "dev")
    assert payload["status"] in ("success", "failed", "partial")
    assert payload["result"] == expected_result_value
    assert isinstance(payload["summary"], str)
    assert len(payload["summary"]) <= 2048
    assert isinstance(payload["artifacts"], dict)
    assert isinstance(payload["next_actions"], list)
    assert all(isinstance(item, str) for item in payload["next_actions"])

    assert "data:image" not in json_text
    assert "image_data" not in json_text
