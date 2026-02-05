from __future__ import annotations

import asyncio
import base64
import importlib
import json
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any

import fastmcp
import pytest
from mcp.types import TextContent


def _configure_memory_docket(monkeypatch: pytest.MonkeyPatch, *, label: str) -> None:
    monkeypatch.setattr(fastmcp.settings.docket, "url", f"memory://{label}")
    monkeypatch.setattr(fastmcp.settings.docket, "name", f"gsd-{label}")


def _import_fresh_entrypoint() -> Any:
    module_name = "gsd_browser.fastmcp_v2_stdio"
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


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


def test_multitenant_denial_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_memory_docket(monkeypatch, label="multitenant-denial-e2e")
    monkeypatch.setenv("GSD_TASK_POLL_INTERVAL_MS", "50")

    monkeypatch.setenv("GSD_S3_ENDPOINT_URL", "http://example.invalid")
    monkeypatch.setenv("GSD_S3_BUCKET", "bucket")
    monkeypatch.setenv("GSD_S3_REGION", "us-east-1")
    monkeypatch.setenv("GSD_S3_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("GSD_S3_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("GSD_S3_SSE_MODE", "none")
    monkeypatch.setenv("GSD_PRESIGNED_URL_TTL_S", "900")
    monkeypatch.setenv("GSD_ARTIFACT_DELIVERY_MODE", "inline")

    from gsd_browser.optionb import s3_client as s3_client_mod
    from gsd_browser.optionb.identity import Identity

    fake_s3 = _FakeS3(bucket="bucket", _objects={})
    monkeypatch.setattr(s3_client_mod, "get_s3_client", lambda: fake_s3)

    entry = _import_fresh_entrypoint()

    identity_holder: dict[str, Identity] = {
        "value": Identity(tenant_id="tA", subject_id="sA", transport="stdio")
    }
    monkeypatch.setattr(
        entry, "_resolve_identity_for_current_call", lambda: identity_holder["value"]
    )
    entry.mcp._resolve_identity_for_current_request = (  # type: ignore[method-assign]
        lambda: identity_holder["value"]
    )

    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/w8AAgMBgR0+"
        "QAAAAABJRU5ErkJggg=="
    )

    async def fake_web_eval_agent(*_args: Any, **_kwargs: Any) -> list[TextContent]:
        from gsd_browser.optionb.run_event_artifacts import persist_run_event_chunk
        from gsd_browser.optionb.screenshot_artifacts import persist_screenshot
        from gsd_browser.screenshot_manager import Screenshot

        session_id = str(uuid.uuid4())
        tool_call_id = str(uuid.uuid4())
        now = time.time()

        shot = Screenshot(
            id=str(uuid.uuid4()),
            timestamp=now,
            screenshot_type="agent_step",
            source="test",
            session_id=session_id,
            has_error=False,
            metadata={},
            image_bytes=png_bytes,
            mime_type="image/png",
            url="http://example.test",
            step=1,
        )

        await persist_screenshot(shot)
        await persist_run_event_chunk(
            session_id=session_id,
            events=[
                {
                    "event_type": "agent",
                    "timestamp": now,
                    "summary": "step 1",
                    "has_error": False,
                    "details": {"step": 1, "url": "http://example.test"},
                }
            ],
        )

        payload = {
            "version": "gsd.web_eval_agent.v1",
            "session_id": session_id,
            "tool_call_id": tool_call_id,
            "url": "http://example.test",
            "task": "x",
            "mode": "compact",
            "requested_mode": "compact",
            "status": "success",
            "result": "ok",
            "summary": "ok",
            "page": {"url": "http://example.test", "title": "Example"},
            "errors_top": [],
            "timeouts": {
                "budget_s": None,
                "step_timeout_s": None,
                "max_steps": None,
                "timed_out": False,
            },
            "warnings": [],
            "artifacts": {"screenshots": 1, "stream_samples": 0, "run_events": 1},
            "next_actions": [],
        }
        await asyncio.sleep(0.05)
        return [TextContent(type="text", text=json.dumps(payload))]

    monkeypatch.setattr(entry.sdk_server, "web_eval_agent", fake_web_eval_agent)

    async def run() -> None:
        from fastmcp import Client
        from mcp.shared.exceptions import McpError

        async with Client(entry.mcp) as client:
            task = await client.call_tool(
                "web_eval_agent",
                {"url": "http://example.test", "task": "x"},
                task=True,
                ttl=60_000,
            )

            deadline = time.time() + 5.0
            status_value: str | None = None
            while time.time() < deadline:
                status = await client.get_task_status(task.task_id)
                status_value = str(getattr(status, "status", "")).strip().lower()
                if status_value in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(0.05)
            assert status_value == "completed"

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
            session_id = str(payload.get("session_id") or "")
            assert session_id

            screenshots_a = await client.call_tool_mcp(
                "get_screenshots",
                {
                    "session_id": session_id,
                    "last_n": 5,
                    "screenshot_type": "agent_step",
                    "include_images": False,
                },
            )
            assert screenshots_a.isError is False
            header_a = screenshots_a.content[0]
            assert isinstance(header_a, TextContent)
            screenshots_payload_a = json.loads(header_a.text)
            assert screenshots_payload_a["session_id"] == session_id
            assert screenshots_payload_a["error"] is None
            assert screenshots_payload_a["screenshots"]

            run_events_a = await client.call_tool_mcp(
                "get_run_events",
                {"session_id": session_id, "last_n": 50, "include_details": False},
            )
            assert run_events_a.isError is False
            header_a2 = run_events_a.content[0]
            assert isinstance(header_a2, TextContent)
            run_events_payload_a = json.loads(header_a2.text)
            assert run_events_payload_a["session_id"] == session_id
            assert run_events_payload_a["error"] is None
            assert run_events_payload_a["events"]

            identity_holder["value"] = Identity(tenant_id="tB", subject_id="sB", transport="stdio")

            with pytest.raises(McpError) as excinfo:
                _ = await client.get_task_status(task.task_id)
            assert "not found" in str(excinfo.value).lower()

            with pytest.raises(McpError) as excinfo:
                _ = await client.get_task_result(task.task_id)
            assert "not found" in str(excinfo.value).lower()

            with pytest.raises(McpError) as excinfo:
                await client.cancel_task(task.task_id)
            assert "not found" in str(excinfo.value).lower()

            screenshots_b = await client.call_tool_mcp(
                "get_screenshots",
                {
                    "session_id": session_id,
                    "last_n": 5,
                    "screenshot_type": "agent_step",
                    "include_images": False,
                },
            )
            assert screenshots_b.isError is False
            header_b = screenshots_b.content[0]
            assert isinstance(header_b, TextContent)
            screenshots_payload_b = json.loads(header_b.text)
            assert screenshots_payload_b["session_id"] == session_id
            assert screenshots_payload_b["error"] is None
            assert screenshots_payload_b["screenshots"] == []

            run_events_b = await client.call_tool_mcp(
                "get_run_events",
                {"session_id": session_id, "last_n": 50, "include_details": False},
            )
            assert run_events_b.isError is False
            header_b2 = run_events_b.content[0]
            assert isinstance(header_b2, TextContent)
            run_events_payload_b = json.loads(header_b2.text)
            assert run_events_payload_b["session_id"] == session_id
            assert run_events_payload_b["error"] is None
            assert run_events_payload_b["events"] == []

    asyncio.run(run())
