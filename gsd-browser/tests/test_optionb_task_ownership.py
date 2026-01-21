from __future__ import annotations

import asyncio
import json
import time

import fastmcp
import pytest
from fastmcp import Client
from fastmcp.server.tasks import TaskConfig
from mcp.shared.exceptions import McpError
from mcp.types import METHOD_NOT_FOUND

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

    # Enable client TTL override so the test can verify the client-provided TTL is used
    monkeypatch.setenv("GSD_TASK_ALLOW_CLIENT_TTL_OVERRIDE", "true")
    from gsd_browser.optionb import task_ttl_policy

    task_ttl_policy.reset_ttl_config_cache()

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
    task_ttl_policy.reset_ttl_config_cache()


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


def test_tasks_list_is_disabled_by_default() -> None:
    server = GsdFastMCP("ownership-test", tasks=True)

    async def run() -> None:
        async with Client(server) as client:
            with pytest.raises(McpError) as exc:
                _ = await client.list_tasks()

            assert exc.value.error.code == METHOD_NOT_FOUND

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


def test_task_ownership_record_uses_server_default_ttl_when_client_provides_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When client doesn't provide TTL, server default for the tool is used."""
    _configure_memory_docket(monkeypatch, label="ttl-server-default")
    now_ms = int(time.time() * 1000)
    monkeypatch.setattr(task_ownership, "_now_ms", lambda: now_ms)

    # Set custom server defaults
    monkeypatch.setenv("GSD_TASK_TTL_WEB_EVAL_AGENT_S", "600")  # 10 minutes

    from gsd_browser.optionb import task_ttl_policy

    task_ttl_policy.reset_ttl_config_cache()

    server = GsdFastMCP("ttl-test", tasks=True)
    server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
        tenant_id="t1",
        subject_id="s1",
        transport="stdio",
    )

    @server.tool(name="web_eval_agent", task=TaskConfig(mode="required"))
    async def web_eval_agent() -> str:
        return "ok"

    async def run() -> None:
        async with Client(server) as client:
            # No ttl provided in the call
            task = await client.call_tool("web_eval_agent", {}, task=True)
            task_id = task.task_id

            docket = server.docket
            assert docket is not None
            async with docket.redis() as redis:
                raw = await redis.get(f"gsd:v1:tasks:{task_id}:owner")

            assert raw is not None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = json.loads(raw)

            # Should use server default of 600s (600,000 ms)
            expected_expires = now_ms + 600_000
            assert payload["expires_at_ms"] == expected_expires

    asyncio.run(run())
    task_ttl_policy.reset_ttl_config_cache()


def test_task_ownership_record_ignores_client_ttl_when_override_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When client provides TTL but override is disabled, server default is used."""
    _configure_memory_docket(monkeypatch, label="ttl-override-disabled")
    now_ms = int(time.time() * 1000)
    monkeypatch.setattr(task_ownership, "_now_ms", lambda: now_ms)

    # Override is disabled by default, but be explicit
    monkeypatch.setenv("GSD_TASK_ALLOW_CLIENT_TTL_OVERRIDE", "false")
    monkeypatch.setenv("GSD_TASK_TTL_WEB_EVAL_AGENT_S", "900")  # 15 minutes

    from gsd_browser.optionb import task_ttl_policy

    task_ttl_policy.reset_ttl_config_cache()

    server = GsdFastMCP("ttl-test", tasks=True)
    server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
        tenant_id="t1",
        subject_id="s1",
        transport="stdio",
    )

    @server.tool(name="web_eval_agent", task=TaskConfig(mode="required"))
    async def web_eval_agent() -> str:
        return "ok"

    async def run() -> None:
        async with Client(server) as client:
            # Client requests 5 minutes, but override is disabled
            task = await client.call_tool("web_eval_agent", {}, task=True, ttl=300_000)
            task_id = task.task_id

            docket = server.docket
            assert docket is not None
            async with docket.redis() as redis:
                raw = await redis.get(f"gsd:v1:tasks:{task_id}:owner")

            assert raw is not None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = json.loads(raw)

            # Should use server default of 900s (900,000 ms), NOT client's 300s
            expected_expires = now_ms + 900_000
            assert payload["expires_at_ms"] == expected_expires

    asyncio.run(run())
    task_ttl_policy.reset_ttl_config_cache()


def test_task_call_rejected_when_client_ttl_exceeds_max(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When client provides TTL above max and override is enabled, call is rejected."""
    _configure_memory_docket(monkeypatch, label="ttl-out-of-bounds")

    # Enable override and set bounds
    monkeypatch.setenv("GSD_TASK_ALLOW_CLIENT_TTL_OVERRIDE", "true")
    monkeypatch.setenv("GSD_TASK_TTL_MIN_S", "60")
    monkeypatch.setenv("GSD_TASK_TTL_MAX_S", "3600")  # 1 hour max

    from gsd_browser.optionb import task_ttl_policy

    task_ttl_policy.reset_ttl_config_cache()

    server = GsdFastMCP("ttl-test", tasks=True)
    server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
        tenant_id="t1",
        subject_id="s1",
        transport="stdio",
    )

    @server.tool(name="web_eval_agent", task=TaskConfig(mode="required"))
    async def web_eval_agent() -> str:
        return "ok"

    async def run() -> None:
        async with Client(server) as client:
            # Client requests 2 hours (above 1 hour max)
            task = await client.call_tool("web_eval_agent", {}, task=True, ttl=7_200_000)

            # Should return immediately with error
            assert task.returned_immediately is True
            result = await task.result()
            assert result.is_error is True

            message = ""
            for entry in result.content:
                if hasattr(entry, "text"):
                    message = str(entry.text)
                    break
            assert "outside allowed bounds" in message.lower()

    asyncio.run(run())
    task_ttl_policy.reset_ttl_config_cache()


def test_task_call_rejected_when_client_ttl_below_min(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When client provides TTL below min and override is enabled, call is rejected."""
    _configure_memory_docket(monkeypatch, label="ttl-below-min")

    # Enable override and set bounds
    monkeypatch.setenv("GSD_TASK_ALLOW_CLIENT_TTL_OVERRIDE", "true")
    monkeypatch.setenv("GSD_TASK_TTL_MIN_S", "120")  # 2 minute min
    monkeypatch.setenv("GSD_TASK_TTL_MAX_S", "7200")

    from gsd_browser.optionb import task_ttl_policy

    task_ttl_policy.reset_ttl_config_cache()

    server = GsdFastMCP("ttl-test", tasks=True)
    server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
        tenant_id="t1",
        subject_id="s1",
        transport="stdio",
    )

    @server.tool(name="web_eval_agent", task=TaskConfig(mode="required"))
    async def web_eval_agent() -> str:
        return "ok"

    async def run() -> None:
        async with Client(server) as client:
            # Client requests 1 minute (below 2 minute min)
            task = await client.call_tool("web_eval_agent", {}, task=True, ttl=60_000)

            # Should return immediately with error
            assert task.returned_immediately is True
            result = await task.result()
            assert result.is_error is True

            message = ""
            for entry in result.content:
                if hasattr(entry, "text"):
                    message = str(entry.text)
                    break
            assert "outside allowed bounds" in message.lower()

    asyncio.run(run())
    task_ttl_policy.reset_ttl_config_cache()


def test_task_ownership_record_uses_client_ttl_when_within_bounds_and_override_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When client provides TTL within bounds and override is enabled, client TTL is used."""
    _configure_memory_docket(monkeypatch, label="ttl-override-enabled")
    now_ms = int(time.time() * 1000)
    monkeypatch.setattr(task_ownership, "_now_ms", lambda: now_ms)

    # Enable override
    monkeypatch.setenv("GSD_TASK_ALLOW_CLIENT_TTL_OVERRIDE", "true")
    monkeypatch.setenv("GSD_TASK_TTL_MIN_S", "60")
    monkeypatch.setenv("GSD_TASK_TTL_MAX_S", "7200")
    monkeypatch.setenv("GSD_TASK_TTL_WEB_EVAL_AGENT_S", "900")

    from gsd_browser.optionb import task_ttl_policy

    task_ttl_policy.reset_ttl_config_cache()

    server = GsdFastMCP("ttl-test", tasks=True)
    server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
        tenant_id="t1",
        subject_id="s1",
        transport="stdio",
    )

    @server.tool(name="web_eval_agent", task=TaskConfig(mode="required"))
    async def web_eval_agent() -> str:
        return "ok"

    async def run() -> None:
        async with Client(server) as client:
            # Client requests 5 minutes (within bounds)
            task = await client.call_tool("web_eval_agent", {}, task=True, ttl=300_000)
            task_id = task.task_id

            docket = server.docket
            assert docket is not None
            async with docket.redis() as redis:
                raw = await redis.get(f"gsd:v1:tasks:{task_id}:owner")

            assert raw is not None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = json.loads(raw)

            # Should use client's 300s (300,000 ms)
            expected_expires = now_ms + 300_000
            assert payload["expires_at_ms"] == expected_expires

    asyncio.run(run())
    task_ttl_policy.reset_ttl_config_cache()
