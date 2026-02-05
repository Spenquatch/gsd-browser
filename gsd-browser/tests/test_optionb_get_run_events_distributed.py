from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass

import fastmcp
import pytest
from fastmcp import Client
from mcp.types import TextContent

from gsd_browser import mcp_server as sdk_server
from gsd_browser.optionb.fastmcp_server import GsdFastMCP
from gsd_browser.optionb.identity import Identity
from gsd_browser.optionb.run_event_artifacts import persist_run_events_from_store
from gsd_browser.run_event_store import RunEventStore


def _configure_memory_docket(monkeypatch: pytest.MonkeyPatch, *, label: str) -> None:
    monkeypatch.setattr(fastmcp.settings.docket, "url", f"memory://{label}")
    monkeypatch.setattr(fastmcp.settings.docket, "name", f"gsd-{label}")


def _configure_fake_s3_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set all required S3 env vars so has_complete_s3_config() returns True."""
    monkeypatch.setenv("GSD_S3_ENDPOINT_URL", "http://example.invalid")
    monkeypatch.setenv("GSD_S3_BUCKET", "test-bucket")
    monkeypatch.setenv("GSD_S3_REGION", "us-east-1")
    monkeypatch.setenv("GSD_S3_ACCESS_KEY_ID", "test-key")
    monkeypatch.setenv("GSD_S3_SECRET_ACCESS_KEY", "test-secret")


@dataclass(frozen=True, slots=True)
class _FakeS3:
    bucket: str
    _objects: dict[str, bytes]

    def put_bytes(self, *, key: str, body: bytes, content_type: str) -> None:  # noqa: ARG002
        self._objects[str(key)] = bytes(body)

    def get_bytes(self, *, key: str) -> bytes:
        return bytes(self._objects.get(str(key), b""))

    def presign_get(self, *, key: str, ttl_s: int) -> tuple[str, float]:
        return f"https://example.test/{key}", float(time.time() + int(ttl_s))


class _DummyRuntime:
    def __init__(self, *, run_events: RunEventStore) -> None:
        self.run_events = run_events

    def ensure_dashboard_running(self, *args: object, **kwargs: object) -> None:
        return None


def test_get_run_events_filters_bounds_and_invalid_input(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_memory_docket(monkeypatch, label="run-events-distributed")
    _configure_fake_s3_env(monkeypatch)

    from gsd_browser.optionb import s3_client as s3_client_mod

    fake_s3 = _FakeS3(bucket="bucket", _objects={})
    monkeypatch.setattr(s3_client_mod, "get_s3_client", lambda: fake_s3)

    store = RunEventStore()
    monkeypatch.setattr(sdk_server, "get_runtime", lambda: _DummyRuntime(run_events=store))

    session_id = str(uuid.uuid4())
    base_ts = time.time()
    server = GsdFastMCP("run-events-test", tasks=True)
    server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
        tenant_id="t1",
        subject_id="s1",
        transport="stdio",
    )

    @server.tool(name="seed_run_events")
    async def seed_run_events() -> None:
        store.ensure_session(session_id, created_at=base_ts)
        store.record_event(
            session_id=session_id,
            event_type="network",
            timestamp=base_ts + 1,
            summary="GET /ok",
            details={"status": 200},
            has_error=False,
        )
        store.record_event(
            session_id=session_id,
            event_type="network",
            timestamp=base_ts + 2,
            summary="GET /boom",
            details={"status": 500},
            has_error=True,
        )
        store.record_event(
            session_id=session_id,
            event_type="console",
            timestamp=base_ts + 3,
            summary="console boom",
            details={"level": "error", "location": {"url": "https://example.test", "line": 1}},
            has_error=True,
        )
        await persist_run_events_from_store(store, session_id=session_id)

    @server.tool(name="get_run_events")
    async def get_run_events_tool(
        session_id: str = "",
        last_n: int = 50,
        event_types: list[str] | None = None,
        from_timestamp: object | None = None,
        has_error: bool | None = None,
        include_details: bool = False,
        ctx: object | None = None,
    ):
        return await sdk_server.get_run_events(
            session_id=session_id,
            last_n=last_n,
            event_types=event_types,
            from_timestamp=from_timestamp,
            has_error=has_error,
            include_details=include_details,
            ctx=ctx,  # type: ignore[arg-type]
        )

    async def run() -> None:
        async with Client(server) as client:
            _ = await client.call_tool("seed_run_events", {})

            result = await client.call_tool_mcp(
                name="get_run_events",
                arguments={"session_id": session_id, "last_n": 200, "event_types": ["console"]},
            )
            assert result.isError is False
            assert isinstance(result.content[0], TextContent)
            payload = json.loads(result.content[0].text)
            assert payload["session_id"] == session_id
            assert payload["error"] is None
            assert len(payload["events"]) == 1
            assert payload["events"][0]["event_type"] == "console"
            assert "details" not in payload["events"][0]

            result = await client.call_tool_mcp(
                name="get_run_events",
                arguments={
                    "session_id": session_id,
                    "last_n": 200,
                    "has_error": True,
                    "include_details": True,
                },
            )
            payload = json.loads(result.content[0].text)
            assert payload["events"]
            assert all(item.get("has_error") is True for item in payload["events"])
            assert any("details" in item for item in payload["events"])

            result = await client.call_tool_mcp(
                name="get_run_events",
                arguments={
                    "session_id": session_id,
                    "from_timestamp": base_ts + 2.5,
                    "last_n": 200,
                },
            )
            payload = json.loads(result.content[0].text)
            assert all(
                float(item.get("timestamp", 0.0)) >= base_ts + 2.5 for item in payload["events"]
            )

            result = await client.call_tool_mcp(
                name="get_run_events",
                arguments={"session_id": session_id, "event_types": ["nope"], "last_n": 50},
            )
            payload = json.loads(result.content[0].text)
            assert payload["session_id"] is None
            assert payload["events"] == []
            assert payload["error"]

            result = await client.call_tool_mcp(
                name="get_run_events",
                arguments={"session_id": session_id, "from_timestamp": "nope"},
            )
            payload = json.loads(result.content[0].text)
            assert payload["session_id"] is None
            assert payload["events"] == []
            assert payload["error"]

    asyncio.run(run())


def test_get_run_events_is_non_enumerable_across_tenants(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_memory_docket(monkeypatch, label="run-events-non-enumerable")
    _configure_fake_s3_env(monkeypatch)

    from gsd_browser.optionb import s3_client as s3_client_mod

    fake_s3 = _FakeS3(bucket="bucket", _objects={})
    monkeypatch.setattr(s3_client_mod, "get_s3_client", lambda: fake_s3)

    store = RunEventStore()
    monkeypatch.setattr(sdk_server, "get_runtime", lambda: _DummyRuntime(run_events=store))

    session_id = str(uuid.uuid4())
    server = GsdFastMCP("run-events-test", tasks=True)

    @server.tool(name="seed_run_events")
    async def seed_run_events() -> None:
        base = time.time()
        store.ensure_session(session_id, created_at=base)
        store.record_event(
            session_id=session_id,
            event_type="network",
            timestamp=base + 1,
            summary="GET /boom",
            details={"status": 500},
            has_error=True,
        )
        await persist_run_events_from_store(store, session_id=session_id)

    @server.tool(name="get_run_events")
    async def get_run_events_tool(
        session_id: str = "",
        last_n: int = 50,
        event_types: list[str] | None = None,
        from_timestamp: object | None = None,
        has_error: bool | None = None,
        include_details: bool = False,
        ctx: object | None = None,
    ):
        return await sdk_server.get_run_events(
            session_id=session_id,
            last_n=last_n,
            event_types=event_types,
            from_timestamp=from_timestamp,
            has_error=has_error,
            include_details=include_details,
            ctx=ctx,  # type: ignore[arg-type]
        )

    async def run() -> None:
        server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
            tenant_id="t1",
            subject_id="s1",
            transport="stdio",
        )
        async with Client(server) as client:
            _ = await client.call_tool("seed_run_events", {})

            server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
                tenant_id="t2",
                subject_id="s2",
                transport="stdio",
            )
            result = await client.call_tool_mcp(
                name="get_run_events",
                arguments={"session_id": session_id, "last_n": 50},
            )
            assert isinstance(result.content[0], TextContent)
            payload = json.loads(result.content[0].text)
            assert payload["session_id"] == session_id
            assert payload["events"] == []
            assert payload["error"] is None

    asyncio.run(run())
