from __future__ import annotations

import asyncio
import importlib
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import fastmcp
import jsonschema
import pytest
from fastmcp import Client
from mcp.types import TextContent

from gsd_browser.contracts.v1 import WebEvalAgentPayloadV1


def _configure_memory_docket(monkeypatch: pytest.MonkeyPatch, *, label: str) -> None:
    monkeypatch.setattr(fastmcp.settings.docket, "url", f"memory://{label}")
    monkeypatch.setattr(fastmcp.settings.docket, "name", f"gsd-{label}")


def _import_fresh_entrypoint() -> Any:
    module_name = "gsd_browser.fastmcp_v2_stdio"
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_tasks_lifecycle_e2e_tasks_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_memory_docket(monkeypatch, label="tasks-lifecycle-e2e-tasks-only")
    monkeypatch.setenv("GSD_TASK_POLL_INTERVAL_MS", "50")

    entry = _import_fresh_entrypoint()

    async def fake_web_eval_agent(*_args: Any, **_kwargs: Any) -> list[TextContent]:
        payload = WebEvalAgentPayloadV1(
            version="gsd.web_eval_agent.v1",
            session_id=uuid.uuid4(),
            tool_call_id=uuid.uuid4(),
            url="http://example.test",
            task="x",
            mode="compact",
            status="success",
            result="ok",
            summary="ok",
            page={"url": "http://example.test", "title": "Example"},
            errors_top=[],
            timeouts={
                "budget_s": None,
                "step_timeout_s": None,
                "max_steps": None,
                "timed_out": False,
            },
            warnings=[],
            artifacts={"screenshots": 0, "stream_samples": 0, "run_events": 0},
            next_actions=[],
        )
        await asyncio.sleep(0.25)
        return [TextContent(type="text", text=payload.model_dump_json())]

    monkeypatch.setattr(entry.sdk_server, "web_eval_agent", fake_web_eval_agent)

    schema_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "api"
        / "jsonschema"
        / "gsd.web_eval_agent.v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)

    async def run() -> None:
        async with Client(entry.mcp) as client:
            task = await client.call_tool(
                "web_eval_agent",
                {"url": "http://example.test", "task": "x"},
                task=True,
                ttl=60_000,
            )

            statuses: list[str] = []
            deadline = time.time() + 5.0
            status_value: str | None = None
            poll_s = 0.05
            while time.time() < deadline:
                status = await client.get_task_status(task.task_id)
                status_value = str(getattr(status, "status", "")).strip().lower()
                statuses.append(status_value)
                poll_s = float(getattr(status, "pollInterval", 50) or 50) / 1000.0
                if status_value in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(min(0.2, poll_s))

            assert statuses
            assert status_value == "completed"
            assert "completed" in statuses
            assert len(set(statuses)) >= 2

            result = await client.get_task_result(task.task_id)
            if isinstance(result, dict):
                assert result.get("isError") is False
                content = list(result.get("content") or [])
            else:
                assert getattr(result, "isError", False) is False
                content = list(getattr(result, "content", None) or [])
            assert content

            first = content[0]
            if isinstance(first, TextContent):
                text_payload = first.text
            elif isinstance(first, dict):
                text_payload = str(first.get("text") or "")
            else:
                text_payload = str(getattr(first, "text", "") or "")

            payload = json.loads(text_payload)

            validator.validate(payload)

    asyncio.run(run())
