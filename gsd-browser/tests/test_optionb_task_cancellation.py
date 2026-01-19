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


def test_task_cancellation_stops_work_stops_progress_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="task-cancellation")

    entry = _import_fresh_entrypoint()
    from gsd_browser.optionb.cancellation import should_propagate_cancelled_error
    from gsd_browser.runtime import get_runtime

    cleanup_called: list[bool] = []
    steps: list[int] = []

    async def fake_web_eval_agent(*_args: Any, **_kwargs: Any) -> list[TextContent]:
        runtime = get_runtime()
        step = 0
        try:
            while True:
                step += 1
                steps.append(step)
                now = time.time()
                runtime.run_events.record_agent_event(
                    "test-session",
                    captured_at=now,
                    step=step,
                    summary=f"step {step}",
                )
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            if should_propagate_cancelled_error():
                raise
            payload = {
                "version": "gsd.web_eval_agent.v1",
                "session_id": "test-session",
                "status": "failed",
                "result": None,
                "summary": "Cancelled.",
            }
            return [TextContent(type="text", text=json.dumps(payload))]
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
            task.on_status_change(
                lambda status: messages.append(status.statusMessage)  # type: ignore[arg-type]
                if status.statusMessage
                else None
            )

            for _ in range(80):
                await asyncio.sleep(0.05)
                if any(msg.startswith("phase=agent_step ") for msg in messages):
                    break

            assert any(msg.startswith("phase=agent_step ") for msg in messages)
            steps_before_cancel = len(steps)

            await client.cancel_task(task.task_id)

            status = None
            for _ in range(60):
                status = await client.get_task_status(task.task_id)
                if status.status == "cancelled":
                    break
                await asyncio.sleep(0.05)
            assert status is not None
            assert status.status == "cancelled"

            for _ in range(60):
                if cleanup_called:
                    break
                await asyncio.sleep(0.05)
            assert cleanup_called

            for _ in range(60):
                if "Task cancelled" in messages:
                    break
                await asyncio.sleep(0.05)

            phase_count_after_cancelled = len([msg for msg in messages if msg.startswith("phase=")])
            steps_after_cancelled = len(steps)

            await asyncio.sleep(0.3)

            phase_count_now = len([msg for msg in messages if msg.startswith("phase=")])
            assert phase_count_now == phase_count_after_cancelled
            assert len(steps) == steps_after_cancelled
            assert steps_before_cancel > 0

    asyncio.run(run())
