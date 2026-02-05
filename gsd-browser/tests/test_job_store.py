from __future__ import annotations

import asyncio
import json
import time
import uuid

import fastmcp
import pytest
from fastmcp import Client
from mcp.types import TextContent

from gsd_browser.optionb import job_store
from gsd_browser.optionb.fastmcp_server import GsdFastMCP
from gsd_browser.optionb.identity import Identity


def _configure_memory_docket(monkeypatch: pytest.MonkeyPatch, *, label: str) -> None:
    monkeypatch.setattr(fastmcp.settings.docket, "url", f"memory://{label}")
    monkeypatch.setattr(fastmcp.settings.docket, "name", f"gsd-{label}")


def _parse_tool_result(result) -> object:  # noqa: ANN001
    if result.content:
        assert isinstance(result.content[0], TextContent)
        return json.loads(result.content[0].text)
    if getattr(result, "structuredContent", None) is not None:
        structured = result.structuredContent
        if isinstance(structured, dict) and "result" in structured:
            return structured["result"]
    raise AssertionError("Unexpected tool result payload shape")


def test_job_store_create_persists_record_and_sets_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_memory_docket(monkeypatch, label="job-store-create")
    monkeypatch.setenv("GSD_DEPLOYMENT_ENV", "dev")
    monkeypatch.setenv("GSD_RETENTION_SECONDS_DEV", "123")

    now_ms = int(time.time() * 1000)
    monkeypatch.setattr(job_store, "_now_ms", lambda: now_ms)

    server = GsdFastMCP("job-store-test", tasks=True)
    server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
        tenant_id="t1",
        subject_id="s1",
        transport="stdio",
    )

    @server.tool(name="create_job_record")
    async def create_job_record(task_id: str, session_id: str) -> dict[str, object]:
        record = await job_store.create_job(
            task_id=task_id,
            tool_name="web_eval_agent",
            session_id=session_id,
        )
        return record.model_dump(mode="json")

    async def run() -> None:
        async with Client(server) as client:
            task_id = str(uuid.uuid4())
            session_id = str(uuid.uuid4())
            result = await client.call_tool_mcp(
                name="create_job_record",
                arguments={"task_id": task_id, "session_id": session_id},
            )
            assert result.isError is False
            record = _parse_tool_result(result)
            assert isinstance(record, dict)
            assert record["version"] == "gsd.job_record.v1"
            assert record["task_id"] == task_id
            assert record["tenant_id"] == "t1"
            assert record["subject_id"] == "s1"
            assert record["transport"] == "stdio"
            assert record["tool_name"] == "web_eval_agent"
            assert record["created_at_ms"] == now_ms
            assert record["expires_at_ms"] == now_ms + 123_000
            assert record["session_id"] == session_id

            job_id = str(record["job_id"])
            parsed = uuid.UUID(job_id)
            assert parsed.version == 4

            docket = server.docket
            assert docket is not None
            key = f"gsd:v1:jobs:{job_id}:record"
            async with docket.redis() as redis:
                raw = await redis.get(key)
                ttl_ms = await redis.pttl(key)

            assert raw is not None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = json.loads(raw)
            assert payload["job_id"] == job_id
            assert ttl_ms != -1

    asyncio.run(run())


def test_job_store_get_is_non_enumerable_across_tenants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="job-store-ownership")
    monkeypatch.setenv("GSD_DEPLOYMENT_ENV", "dev")
    monkeypatch.setenv("GSD_RETENTION_SECONDS_DEV", "60")

    server = GsdFastMCP("job-store-test", tasks=True)

    @server.tool(name="create_job_record")
    async def create_job_record(task_id: str, session_id: str) -> dict[str, object]:
        record = await job_store.create_job(
            task_id=task_id,
            tool_name="web_eval_agent",
            session_id=session_id,
        )
        return record.model_dump(mode="json")

    @server.tool(name="get_job_record")
    async def get_job_record(job_id: str) -> dict[str, object] | None:
        record = await job_store.get_job(job_id)
        return None if record is None else record.model_dump(mode="json")

    async def run() -> None:
        server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
            tenant_id="t1",
            subject_id="s1",
            transport="stdio",
        )
        async with Client(server) as client:
            create_result = await client.call_tool_mcp(
                name="create_job_record",
                arguments={"task_id": str(uuid.uuid4()), "session_id": str(uuid.uuid4())},
            )
            assert create_result.isError is False
            created = _parse_tool_result(create_result)
            assert isinstance(created, dict)
            job_id = str(created["job_id"])

            found_result = await client.call_tool_mcp(
                name="get_job_record",
                arguments={"job_id": job_id},
            )
            assert found_result.isError is False
            found = _parse_tool_result(found_result)
            assert isinstance(found, dict)
            assert found["job_id"] == job_id

            server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
                tenant_id="t2",
                subject_id="s2",
                transport="stdio",
            )
            denied_result = await client.call_tool_mcp(
                name="get_job_record",
                arguments={"job_id": job_id},
            )
            assert denied_result.isError is False
            denied = _parse_tool_result(denied_result)
            assert denied is None

    asyncio.run(run())


def test_job_store_rejects_invalid_job_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_memory_docket(monkeypatch, label="job-store-invalid-id")
    server = GsdFastMCP("job-store-test", tasks=True)

    async def run() -> None:
        async with Client(server):
            docket = server.docket
            assert docket is not None
            store = job_store.JobStore(docket_getter=lambda: docket)
            with pytest.raises(ValueError):
                _ = await store.get("not-a-uuid")

    asyncio.run(run())
