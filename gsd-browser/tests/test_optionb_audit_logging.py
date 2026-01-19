from __future__ import annotations

import asyncio
import logging
import uuid

import fastmcp
import pytest
from fastmcp import Client
from fastmcp.server.tasks import TaskConfig
from mcp.shared.exceptions import McpError

from gsd_browser.optionb.fastmcp_server import GsdFastMCP
from gsd_browser.optionb.identity import Identity


def _configure_memory_docket(monkeypatch: pytest.MonkeyPatch, *, label: str) -> None:
    monkeypatch.setattr(fastmcp.settings.docket, "url", f"memory://{label}")
    monkeypatch.setattr(fastmcp.settings.docket, "name", f"gsd-{label}")


def test_denied_task_access_emits_audit_log_without_leaking_existence(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _configure_memory_docket(monkeypatch, label="audit-task-access-denied")

    server = GsdFastMCP("audit-test", tasks=True)

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

            caplog.set_level(logging.WARNING, logger="gsd_browser.optionb.fastmcp_server")
            server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
                tenant_id="t2",
                subject_id="s2",
                transport="stdio",
            )

            with pytest.raises(McpError):
                _ = await client.get_task_status(task_id)

            denied = [r for r in caplog.records if r.getMessage() == "audit.task_access_denied"]
            assert denied
            record = denied[-1]
            assert getattr(record, "task_id", None) == task_id
            assert getattr(record, "caller_tenant_id", None) == "t2"
            assert getattr(record, "caller_subject_id", None) == "s2"
            assert getattr(record, "caller_transport", None) == "stdio"
            assert getattr(record, "owner_tenant_id", None) == "t1"
            assert getattr(record, "owner_subject_id", None) == "s1"
            assert getattr(record, "owner_transport", None) == "stdio"
            assert getattr(record, "tool_name", None) == "long_tool"
            assert isinstance(getattr(record, "session_id", None), str)

    asyncio.run(run())


def test_artifact_list_queries_emit_structured_audit_logs(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _configure_memory_docket(monkeypatch, label="audit-artifact-list")

    import importlib
    import sys

    module_name = "gsd_browser.fastmcp_v2_stdio"
    sys.modules.pop(module_name, None)
    entry = importlib.import_module(module_name)

    async def run() -> None:
        caplog.set_level(logging.INFO, logger="gsd_browser.fastmcp_v2")
        session_id = str(uuid.uuid4())

        async with Client(entry.mcp) as client:
            _ = await client.call_tool(
                "get_run_events",
                {
                    "session_id": session_id,
                    "last_n": 12,
                    "event_types": ["console"],
                    "has_error": True,
                    "include_details": False,
                },
            )
            _ = await client.call_tool(
                "get_screenshots",
                {
                    "session_id": session_id,
                    "last_n": 3,
                    "screenshot_type": "agent_step",
                    "has_error": False,
                    "include_images": False,
                },
            )

        records = [r for r in caplog.records if r.getMessage() == "audit.artifact_list_query"]
        assert len(records) >= 2

        run_events_record = next(
            (r for r in records if getattr(r, "artifact_kind", None) == "run_events"),
            None,
        )
        assert run_events_record is not None
        assert getattr(run_events_record, "tenant_id", None) == "local"
        assert getattr(run_events_record, "subject_id", None) == "local"
        assert getattr(run_events_record, "transport", None) == "stdio"
        assert getattr(run_events_record, "session_id", None) == session_id
        assert getattr(run_events_record, "last_n", None) == 12
        assert getattr(run_events_record, "event_types", None) == ["console"]
        assert getattr(run_events_record, "has_error", None) is True
        assert getattr(run_events_record, "include_details", None) is False

        screenshots_record = next(
            (r for r in records if getattr(r, "artifact_kind", None) == "screenshots"),
            None,
        )
        assert screenshots_record is not None
        assert getattr(screenshots_record, "tenant_id", None) == "local"
        assert getattr(screenshots_record, "subject_id", None) == "local"
        assert getattr(screenshots_record, "transport", None) == "stdio"
        assert getattr(screenshots_record, "session_id", None) == session_id
        assert getattr(screenshots_record, "last_n", None) == 3
        assert getattr(screenshots_record, "screenshot_type", None) == "agent_step"
        assert getattr(screenshots_record, "has_error", None) is False
        assert getattr(screenshots_record, "include_images", None) is False

    asyncio.run(run())
