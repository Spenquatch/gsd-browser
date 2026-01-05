from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest

from gsd_browser import mcp_server as mcp_server_mod


def _run(value: Any) -> Any:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


class _DummyRuntime:
    def __init__(self) -> None:
        class _DummyScreenshots:
            current_session_id: str | None = None
            current_session_start: float | None = None

        self.screenshots = _DummyScreenshots()

    def ensure_dashboard_running(self, *args: Any, **kwargs: Any) -> None:
        return None


def test_c2_prompt_wrapper_includes_stop_conditions_and_anchor_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_server_mod, "get_runtime", lambda: _DummyRuntime())
    monkeypatch.setattr(mcp_server_mod, "load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        mcp_server_mod,
        "create_browser_use_llms",
        lambda *args, **kwargs: type("DummyLLMs", (), {"primary": object(), "fallback": None})(),
    )

    created_kwargs: dict[str, Any] = {}

    class DummyHistory:
        history: list[object] = []

        def final_result(self) -> str | None:
            return "ok"

        def has_errors(self) -> bool:
            return False

        def errors(self) -> list[object]:
            return []

    class DummyAgent:
        def __init__(
            self,
            *,
            task: str,
            llm: object,
            browser_session: object,
            extend_system_message: str | None = None,
            override_system_message: str | None = None,
            **kwargs: Any,
        ) -> None:
            del task, llm, browser_session
            created_kwargs.update(kwargs)
            if extend_system_message is not None:
                created_kwargs["extend_system_message"] = extend_system_message
            if override_system_message is not None:
                created_kwargs["override_system_message"] = override_system_message

        async def run(self, *args: Any, **kwargs: Any) -> DummyHistory:
            return DummyHistory()

    class DummyBrowserSession:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

    monkeypatch.setattr(
        mcp_server_mod, "_load_browser_use_classes", lambda: (DummyAgent, DummyBrowserSession)
    )

    _run(
        mcp_server_mod.web_eval_agent(
            url="example.com",
            task="check the navbar",
            ctx=object(),
            headless_browser=True,
        )
    )

    prompt_wrapper = created_kwargs.get("override_system_message") or created_kwargs.get(
        "extend_system_message"
    )
    if not isinstance(prompt_wrapper, str):
        pytest.skip("C2 prompt wrapper not yet wired via browser-use Agent system message surfaces")

    lowered = prompt_wrapper.lower()

    expected_base_url = mcp_server_mod._normalize_url("example.com")  # noqa: SLF001
    assert expected_base_url in prompt_wrapper

    assert "login" in lowered
    assert "stop" in lowered
    assert any(token in lowered for token in ("captcha", "bot wall", "botwall", "bot"))
    assert any(token in lowered for token in ("impossible", "site restriction", "restricted"))
    assert "result" in lowered
    assert "retry" in lowered

    assert any(
        token in lowered
        for token in (
            "anchor",
            "base url",
            "avoid navigating away",
            "do not navigate away",
            "don't navigate away",
            "stay on",
            "don't leave",
            "do not leave",
        )
    )
