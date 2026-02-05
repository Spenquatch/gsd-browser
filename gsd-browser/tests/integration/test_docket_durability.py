from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import uuid4

import fastmcp
import pytest
import redis
from docket import Docket
from fastmcp import Client, FastMCP
from fastmcp.server.tasks import TaskConfig

from gsd_browser.optionb.task_backend import require_docket_redis_url


def _redis_ready(url: str) -> bool:
    client = redis.Redis.from_url(url, decode_responses=True)
    try:
        return bool(client.ping())
    except Exception:  # noqa: BLE001
        return False


def test_docket_task_result_persists_across_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    docket_url = "redis://localhost:6379/0"
    if not _redis_ready(docket_url):
        pytest.skip(
            "Redis/Valkey not available at redis://localhost:6379/0. "
            "Start with `docker compose -f docker/compose.redistest.yml up -d`."
        )

    docket_name = f"gsd-test-{uuid4().hex[:8]}"
    monkeypatch.setenv("FASTMCP_DOCKET_URL", docket_url)

    # Ensure FastMCP uses the same URL/name in this process.
    _ = require_docket_redis_url()
    fastmcp.settings.docket.name = docket_name

    server = FastMCP("durability-test", tasks=True)

    @server.tool(name="durable_add", task=TaskConfig(mode="required"))
    async def durable_add(value: int) -> int:
        return value + 1

    async def run_task() -> str:
        async with Client(server) as client:
            task = await client.call_tool("durable_add", {"value": 41}, task=True, ttl=60_000)
            await task.result()
            return task.task_id

    task_id = asyncio.run(run_task())

    redis_client = redis.Redis.from_url(docket_url, decode_responses=True)
    mapping_keys = list(redis_client.scan_iter(match=f"{docket_name}:fastmcp:task:*:{task_id}"))
    assert len(mapping_keys) == 1

    mapping_key = mapping_keys[0]
    task_key = redis_client.get(mapping_key)
    assert isinstance(task_key, str) and task_key

    session_id = task_key.split(":", 1)[0]
    created_at_key = f"{docket_name}:fastmcp:task:{session_id}:{task_id}:created_at"

    async def fetch_result() -> Any:
        async with Docket(name=docket_name, url=docket_url) as docket:
            execution = await docket.get_execution(task_key)
            assert execution is not None
            await execution.sync()
            return await execution.get_result(timeout=timedelta(seconds=0))

    raw_result = asyncio.run(fetch_result())
    assert raw_result == 42

    redis_client.delete(mapping_key, created_at_key)
