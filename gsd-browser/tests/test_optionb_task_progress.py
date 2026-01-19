from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import fastmcp
import pytest
from fastmcp import Client
from mcp.types import TextContent


def _configure_memory_docket(monkeypatch: pytest.MonkeyPatch, *, label: str) -> None:
    monkeypatch.setattr(fastmcp.settings.docket, "url", f"memory://{label}")
    monkeypatch.setattr(fastmcp.settings.docket, "name", f"gsd-{label}")


def _import_fresh_entrypoint() -> object:
    import importlib
    import sys

    module_name = "gsd_browser.fastmcp_v2_stdio"
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_long_tools_return_task_and_advertise_poll_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="task-progress-pollinterval")
    monkeypatch.setenv("GSD_TASK_POLL_INTERVAL_MS", "2345")

    entry = _import_fresh_entrypoint()

    async def fake_long_tool(*_args: Any, **_kwargs: Any) -> list[TextContent]:
        payload = {
            "version": "gsd.web_eval_agent.v1",
            "session_id": "test-session",
            "status": "success",
            "result": {"ok": True},
        }
        return [TextContent(type="text", text=json.dumps(payload))]

    monkeypatch.setattr(entry.sdk_server, "web_eval_agent", fake_long_tool)
    monkeypatch.setattr(entry.sdk_server, "web_task_agent", fake_long_tool)
    monkeypatch.setattr(entry.sdk_server, "web_task_agent_github", fake_long_tool)

    async def run() -> None:
        async with Client(entry.mcp) as client:
            for tool_name in ("web_eval_agent", "web_task_agent", "web_task_agent_github"):
                result = await client.call_tool_mcp(
                    tool_name,
                    {"url": "http://example.test", "task": "x"},
                    meta={"modelcontextprotocol.io/task": {"ttl": 60_000}},
                )
                task_meta = (result.meta or {}).get("modelcontextprotocol.io/task") or {}
                assert task_meta.get("pollInterval") == 2345

                task = await client.call_tool(
                    tool_name,
                    {"url": "http://example.test", "task": "x"},
                    task=True,
                    ttl=60_000,
                )
                assert task.returned_immediately is False

                status = await client.get_task_status(task.task_id)
                assert status.pollInterval == 2345

    asyncio.run(run())


def test_progress_notifications_emitted_start_step_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="task-progress-notifications")

    entry = _import_fresh_entrypoint()
    from gsd_browser.runtime import get_runtime

    async def fake_web_eval_agent(*_args: Any, **_kwargs: Any) -> list[TextContent]:
        await asyncio.sleep(0.05)
        runtime = get_runtime()
        now = time.time()
        runtime.run_events.record_agent_event(
            "test-session", captured_at=now, step=1, summary="step 1"
        )
        runtime.run_events.record_agent_event(
            "test-session", captured_at=now + 0.01, step=2, summary="step 2"
        )
        payload = {
            "version": "gsd.web_eval_agent.v1",
            "session_id": "test-session",
            "status": "success",
            "result": {"ok": True},
        }
        return [TextContent(type="text", text=json.dumps(payload))]

    monkeypatch.setattr(entry.sdk_server, "web_eval_agent", fake_web_eval_agent)

    async def run() -> None:
        messages: list[str] = []

        async with Client(entry.mcp) as client:
            task = await client.call_tool(
                "web_eval_agent",
                {"url": "http://example.test", "task": "x", "max_steps": 2},
                task=True,
                ttl=60_000,
            )
            task.on_status_change(
                lambda status: messages.append(status.statusMessage)  # type: ignore[arg-type]
                if status.statusMessage
                else None
            )
            await task.wait(timeout=5.0)
            await asyncio.sleep(0.1)

        phase_messages = [msg for msg in messages if msg.startswith("phase=")]
        assert any(msg.startswith("phase=init ") for msg in phase_messages)
        assert any(msg.startswith("phase=agent_step ") for msg in phase_messages)
        assert any(msg.startswith("phase=done ") for msg in phase_messages)

    asyncio.run(run())


def test_progress_emitted_on_early_error_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="task-progress-early-error")

    entry = _import_fresh_entrypoint()

    async def fake_web_eval_agent(*_args: Any, **_kwargs: Any) -> list[TextContent]:
        payload = {
            "version": "gsd.web_eval_agent.v1",
            "session_id": "test-session",
            "status": "failed",
            "result": None,
        }
        return [TextContent(type="text", text=json.dumps(payload))]

    monkeypatch.setattr(entry.sdk_server, "web_eval_agent", fake_web_eval_agent)

    async def run() -> None:
        messages: list[str] = []

        async with Client(entry.mcp) as client:
            task = await client.call_tool(
                "web_eval_agent",
                {"url": "http://example.test", "task": "x", "max_steps": 2},
                task=True,
                ttl=60_000,
            )
            task.on_status_change(
                lambda status: messages.append(status.statusMessage)  # type: ignore[arg-type]
                if status.statusMessage
                else None
            )
            await task.wait(timeout=5.0)
            await asyncio.sleep(0.1)

        phase_messages = [msg for msg in messages if msg.startswith("phase=")]
        assert any(msg.startswith("phase=init ") for msg in phase_messages)
        assert any(msg.startswith("phase=failed ") for msg in phase_messages)

    asyncio.run(run())
