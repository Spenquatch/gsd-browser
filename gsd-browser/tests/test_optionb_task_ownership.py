from __future__ import annotations

import asyncio
import json
import time

import fastmcp
import pytest
from fastmcp import Client
from fastmcp.server.tasks import TaskConfig
from mcp.shared.exceptions import McpError

from gsd_browser.optionb import task_ownership
from gsd_browser.optionb.fastmcp_server import GsdFastMCP
from gsd_browser.optionb.identity import Identity


def _configure_memory_docket(monkeypatch: pytest.MonkeyPatch, *, label: str) -> None:
    monkeypatch.setattr(fastmcp.settings.docket, "url", f"memory://{label}")
    monkeypatch.setattr(fastmcp.settings.docket, "name", f"gsd-{label}")


def test_task_ownership_record_is_written_before_returning_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="ownership-record-write")
    now_ms = int(time.time() * 1000)
    monkeypatch.setattr(task_ownership, "_now_ms", lambda: now_ms)

    server = GsdFastMCP("ownership-test", tasks=True)
    server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
        tenant_id="t1",
        subject_id="s1",
        transport="stdio",
    )

    @server.tool(name="long_tool", task=TaskConfig(mode="required"))
    async def long_tool() -> str:
        return "ok"

    async def run() -> None:
        async with Client(server) as client:
            task = await client.call_tool("long_tool", {}, task=True, ttl=60_000)
            task_id = task.task_id

            docket = server.docket
            assert docket is not None
            async with docket.redis() as redis:
                raw = await redis.get(f"gsd:v1:tasks:{task_id}:owner")

            assert raw is not None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = json.loads(raw)

            assert payload["version"] == "gsd.task_ownership.v1"
            assert payload["task_id"] == task_id
            assert payload["tenant_id"] == "t1"
            assert payload["subject_id"] == "s1"
            assert payload["transport"] == "stdio"
            assert payload["tool_name"] == "long_tool"
            assert payload["created_at_ms"] == now_ms
            assert payload["expires_at_ms"] == now_ms + 60_000
            assert isinstance(payload["session_id"], str) and payload["session_id"]

    asyncio.run(run())


def test_tasks_get_result_cancel_are_non_enumerable_across_tenants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="ownership-non-enumerability")

    server = GsdFastMCP("ownership-test", tasks=True)

    @server.tool(name="long_tool", task=TaskConfig(mode="required"))
    async def long_tool() -> str:
        return "ok"

    async def run() -> None:
        server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
            tenant_id="t1",
            subject_id="s1",
            transport="stdio",
        )
        async with Client(server) as client:
            task = await client.call_tool("long_tool", {}, task=True, ttl=60_000)
            task_id = task.task_id

            server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
                tenant_id="t2",
                subject_id="s2",
                transport="stdio",
            )
            with pytest.raises(McpError):
                _ = await client.get_task_status(task_id)
            with pytest.raises(McpError):
                _ = await client.get_task_result(task_id)
            with pytest.raises(McpError):
                _ = await client.cancel_task(task_id)

    asyncio.run(run())


def test_ownership_write_failure_aborts_call_and_attempts_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="ownership-write-failure")

    class _FailingStore:
        async def write(self, _record: task_ownership.TaskOwnershipRecord) -> None:
            raise RuntimeError("redis unavailable")

    server = GsdFastMCP("ownership-test", tasks=True)
    cancelled: list[tuple[str, str, str]] = []

    async def record_cancel(*, task_id: str, tool_name: str, session_id: str) -> None:
        cancelled.append((task_id, tool_name, session_id))

    server._cancel_task_best_effort = record_cancel  # type: ignore[method-assign]
    server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
        tenant_id="t1",
        subject_id="s1",
        transport="stdio",
    )
    monkeypatch.setattr(task_ownership, "get_task_ownership_store", lambda: _FailingStore())

    @server.tool(name="long_tool", task=TaskConfig(mode="required"))
    async def long_tool() -> str:
        return "ok"

    async def run() -> None:
        async with Client(server) as client:
            task = await client.call_tool("long_tool", {}, task=True, ttl=60_000)
            assert task.returned_immediately is True
            result = await task.result()
            assert result.is_error is True
            message = ""
            for entry in result.content:
                if hasattr(entry, "text"):
                    message = str(entry.text)
                    break
            assert "persist task ownership" in message.lower()

    asyncio.run(run())
    assert cancelled
