from __future__ import annotations

import asyncio
import importlib
import sys
import time
import uuid
from typing import Any

import fastmcp
import pytest
from fastmcp import Client
from mcp.types import TextContent


def _configure_memory_docket(monkeypatch: pytest.MonkeyPatch, *, label: str) -> None:
    monkeypatch.setattr(fastmcp.settings.docket, "url", f"memory://{label}")
    monkeypatch.setattr(fastmcp.settings.docket, "name", f"gsd-{label}")


def _import_fresh_entrypoint() -> Any:
    module_name = "gsd_browser.fastmcp_v2_stdio"
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_tasks_cancellation_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_memory_docket(monkeypatch, label="tasks-cancellation-e2e")
    monkeypatch.setenv("GSD_TASK_POLL_INTERVAL_MS", "50")

    entry = _import_fresh_entrypoint()

    from gsd_browser.runtime import get_runtime

    cleanup_called: list[bool] = []
    cancelled_seen: list[bool] = []
    steps: list[int] = []

    async def fake_web_eval_agent(*_args: Any, **_kwargs: Any) -> list[TextContent]:
        runtime = get_runtime()
        session_id = str(uuid.uuid4())
        step = 0
        try:
            while True:
                step += 1
                steps.append(step)
                runtime.run_events.record_agent_event(
                    session_id,
                    captured_at=time.time(),
                    step=step,
                    summary=f"step {step}",
                )
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            cancelled_seen.append(True)
            raise
        finally:
            cleanup_called.append(True)

    monkeypatch.setattr(entry.sdk_server, "web_eval_agent", fake_web_eval_agent)

    async def run() -> None:
        async with Client(entry.mcp) as client:
            task = await client.call_tool(
                "web_eval_agent",
                {"url": "http://example.test", "task": "x", "max_steps": 10},
                task=True,
                ttl=60_000,
            )

            messages: list[str] = []

            def on_status_change(status: Any) -> None:
                message = getattr(status, "statusMessage", None)
                if message:
                    messages.append(str(message))

            task.on_status_change(on_status_change)

            deadline = time.time() + 5.0
            while time.time() < deadline:
                await asyncio.sleep(0.05)
                if any(msg.startswith("phase=agent_step ") for msg in messages):
                    break
            assert any(msg.startswith("phase=agent_step ") for msg in messages)

            steps_before_cancel = len(steps)
            assert steps_before_cancel > 0

            await client.cancel_task(task.task_id)

            deadline = time.time() + 5.0
            status_value: str | None = None
            while time.time() < deadline:
                status = await client.get_task_status(task.task_id)
                status_value = str(getattr(status, "status", "")).strip().lower()
                if status_value == "cancelled":
                    break
                await asyncio.sleep(0.05)
            assert status_value == "cancelled"

            deadline = time.time() + 2.0
            while time.time() < deadline and not cleanup_called:
                await asyncio.sleep(0.05)
            assert cleanup_called
            assert cancelled_seen

            deadline = time.time() + 2.0
            while time.time() < deadline:
                if any(msg.startswith("phase=cancelled ") for msg in messages):
                    break
                await asyncio.sleep(0.05)

            await asyncio.sleep(0.2)

            messages_after_cancelled = len(messages)
            phase_messages_after_cancelled = sum(1 for msg in messages if msg.startswith("phase="))
            steps_after_cancelled = len(steps)

            await asyncio.sleep(0.3)

            assert len(messages) == messages_after_cancelled
            phase_messages_now = sum(1 for msg in messages if msg.startswith("phase="))
            assert phase_messages_now == phase_messages_after_cancelled
            assert len(steps) == steps_after_cancelled

    asyncio.run(run())
