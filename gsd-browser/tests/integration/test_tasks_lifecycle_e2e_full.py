from __future__ import annotations

import asyncio
import base64
import importlib
import json
import socket
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import boto3
import fastmcp
import jsonschema
import pytest
import redis
from botocore.config import Config
from fastmcp import Client
from mcp.types import ImageContent, TextContent

from gsd_browser.contracts.v1 import WebEvalAgentPayloadV1
from gsd_browser.optionb.task_backend import require_docket_redis_url


def _import_fresh_entrypoint() -> Any:
    module_name = "gsd_browser.fastmcp_v2_stdio"
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _is_endpoint_reachable(host: str, port: int, *, timeout_s: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _redis_ready(url: str) -> bool:
    client = redis.Redis.from_url(url, decode_responses=True)
    try:
        return bool(client.ping())
    except Exception:  # noqa: BLE001
        return False


def _ensure_s3_bucket(
    *,
    endpoint_url: str,
    bucket: str,
    region: str,
    access_key_id: str,
    secret_access_key: str,
    timeout_s: float = 30.0,
) -> None:
    session = boto3.session.Session(
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=region,
    )
    raw = session.client(
        "s3",
        endpoint_url=endpoint_url,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )

    deadline = time.time() + float(timeout_s)
    last_exc: Exception | None = None
    while time.time() < deadline:
        try:
            _ = raw.list_buckets()
            last_exc = None
            break
        except Exception as exc:  # pragma: no cover - depends on local docker timing
            last_exc = exc
            time.sleep(0.5)
    if last_exc is not None:
        raise AssertionError(f"S3 endpoint did not become ready within {timeout_s}s: {last_exc}")

    try:
        raw.create_bucket(Bucket=bucket)
    except Exception:
        pass


@pytest.mark.integration
def test_tasks_lifecycle_e2e_full_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    docket_url = "redis://localhost:6379/0"
    if not _redis_ready(docket_url):
        pytest.skip(
            "Redis/Valkey not available at redis://localhost:6379/0. "
            "Start with `docker compose -f docker/compose.redistest.yml up -d`."
        )

    endpoint_url = "http://localhost:8333"
    if not _is_endpoint_reachable("localhost", 8333):
        pytest.skip(
            f"S3 test endpoint not reachable at {endpoint_url}. Start it with: "
            "docker compose -f docker/compose.yml -f docker/compose.s3test.yml up -d"
        )

    monkeypatch.setenv("FASTMCP_DOCKET_URL", docket_url)
    _ = require_docket_redis_url()
    fastmcp.settings.docket.name = f"gsd-e2e-full-{uuid.uuid4().hex[:8]}"

    monkeypatch.setenv("GSD_S3_ENDPOINT_URL", endpoint_url)
    monkeypatch.setenv("GSD_S3_BUCKET", "gsd-s3test")
    monkeypatch.setenv("GSD_S3_REGION", "us-east-1")
    monkeypatch.setenv("GSD_S3_ACCESS_KEY_ID", "gsd_s3test_access")
    monkeypatch.setenv("GSD_S3_SECRET_ACCESS_KEY", "gsd_s3test_secret")
    monkeypatch.setenv("GSD_S3_SSE_MODE", "none")
    monkeypatch.setenv("GSD_ARTIFACT_DELIVERY_MODE", "inline")
    monkeypatch.setenv("GSD_TASK_POLL_INTERVAL_MS", "50")

    _ensure_s3_bucket(
        endpoint_url=endpoint_url,
        bucket="gsd-s3test",
        region="us-east-1",
        access_key_id="gsd_s3test_access",
        secret_access_key="gsd_s3test_secret",
        timeout_s=30.0,
    )

    from gsd_browser.optionb import s3_client as s3_client_mod

    s3_client_mod._client = None

    entry = _import_fresh_entrypoint()

    web_schema_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "api"
        / "jsonschema"
        / "gsd.web_eval_agent.v1.schema.json"
    )
    screenshots_schema_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "api"
        / "jsonschema"
        / "gsd.get_screenshots.v1.schema.json"
    )
    run_events_schema_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "api"
        / "jsonschema"
        / "gsd.get_run_events.v1.schema.json"
    )
    web_validator = jsonschema.Draft202012Validator(
        json.loads(web_schema_path.read_text(encoding="utf-8"))
    )
    screenshots_validator = jsonschema.Draft202012Validator(
        json.loads(screenshots_schema_path.read_text(encoding="utf-8"))
    )
    run_events_validator = jsonschema.Draft202012Validator(
        json.loads(run_events_schema_path.read_text(encoding="utf-8"))
    )

    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/w8AAgMBgR0+"
        "QAAAAABJRU5ErkJggg=="
    )

    async def fake_web_eval_agent(*_args: Any, **_kwargs: Any) -> list[TextContent]:
        from gsd_browser.optionb.run_event_artifacts import persist_run_event_chunk
        from gsd_browser.optionb.screenshot_artifacts import persist_screenshot
        from gsd_browser.screenshot_manager import Screenshot

        session_uuid = uuid.uuid4()
        tool_call_uuid = uuid.uuid4()
        now = time.time()

        shot = Screenshot(
            id=str(uuid.uuid4()),
            timestamp=now,
            screenshot_type="agent_step",
            source="test",
            session_id=str(session_uuid),
            has_error=False,
            metadata={},
            image_bytes=png_bytes,
            mime_type="image/png",
            url="http://example.test",
            step=1,
        )

        await persist_screenshot(shot)
        await persist_run_event_chunk(
            session_id=str(session_uuid),
            events=[
                {
                    "event_type": "agent",
                    "timestamp": now,
                    "summary": "step 1",
                    "has_error": False,
                    "details": {"step": 1, "url": "http://example.test"},
                },
                {
                    "event_type": "console",
                    "timestamp": now + 0.01,
                    "summary": "console error",
                    "has_error": True,
                    "details": {
                        "level": "error",
                        "location": {"url": "http://example.test", "line": 1, "column": 1},
                    },
                },
                {
                    "event_type": "network",
                    "timestamp": now + 0.02,
                    "summary": "GET http://example.test",
                    "has_error": False,
                    "details": {"method": "GET", "url": "http://example.test", "status": 200},
                },
            ],
        )

        payload = WebEvalAgentPayloadV1(
            version="gsd.web_eval_agent.v1",
            session_id=session_uuid,
            tool_call_id=tool_call_uuid,
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
            artifacts={"screenshots": 1, "stream_samples": 0, "run_events": 3},
            next_actions=[],
        )

        await asyncio.sleep(0.25)
        return [TextContent(type="text", text=payload.model_dump_json())]

    monkeypatch.setattr(entry.sdk_server, "web_eval_agent", fake_web_eval_agent)

    async def run() -> None:
        async with Client(entry.mcp) as client:
            task = await client.call_tool(
                "web_eval_agent",
                {"url": "http://example.test", "task": "x"},
                task=True,
                ttl=60_000,
            )

            deadline = time.time() + 10.0
            statuses: list[str] = []
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
            web_validator.validate(payload)
            session_id = payload["session_id"]
            assert isinstance(session_id, str) and session_id

            screenshots_result = await client.call_tool_mcp(
                "get_screenshots",
                {
                    "session_id": session_id,
                    "last_n": 5,
                    "screenshot_type": "agent_step",
                    "include_images": True,
                },
            )
            assert screenshots_result.isError is False
            assert screenshots_result.content

            header = screenshots_result.content[0]
            assert isinstance(header, TextContent)
            screenshots_payload = json.loads(header.text)
            screenshots_validator.validate(screenshots_payload)

            screenshots = list(screenshots_payload.get("screenshots") or [])
            assert len(screenshots) == 1
            assert screenshots[0]["session_id"] == session_id
            assert screenshots[0]["inline_included"] is True
            assert screenshots[0]["artifact"]["url"] is None
            assert screenshots[0]["artifact"]["size_bytes"] == len(png_bytes)

            images = [item for item in screenshots_result.content[1:] if isinstance(item, ImageContent)]
            assert len(images) == 1

            screenshots_meta_only = await client.call_tool_mcp(
                "get_screenshots",
                {
                    "session_id": session_id,
                    "last_n": 5,
                    "screenshot_type": "agent_step",
                    "include_images": False,
                },
            )
            assert screenshots_meta_only.isError is False
            header2 = screenshots_meta_only.content[0]
            assert isinstance(header2, TextContent)
            screenshots_payload2 = json.loads(header2.text)
            screenshots_validator.validate(screenshots_payload2)
            assert screenshots_payload2["screenshots"][0]["inline_included"] is False
            assert len(screenshots_meta_only.content) == 1

            run_events_result = await client.call_tool_mcp(
                "get_run_events",
                {"session_id": session_id, "last_n": 50, "include_details": False},
            )
            assert run_events_result.isError is False
            assert run_events_result.content
            run_events_header = run_events_result.content[0]
            assert isinstance(run_events_header, TextContent)
            run_events_payload = json.loads(run_events_header.text)
            run_events_validator.validate(run_events_payload)

            events = list(run_events_payload.get("events") or [])
            assert len(events) >= 3
            assert all("details" not in event for event in events)

    asyncio.run(run())

