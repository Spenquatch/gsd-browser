from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import timedelta
from typing import Any

import fastmcp
from mcp.types import TextContent

from gsd_browser.contracts.v1 import WebEvalAgentPayloadV1
from gsd_browser.optionb.identity import Identity
from gsd_browser.optionb.task_backend import require_docket_redis_url


def _env(name: str, default: str) -> str:
    value = str(os.environ.get(name, "")).strip()
    return value if value else default


def _configure_docket() -> None:
    _ = require_docket_redis_url()
    fastmcp.settings.docket.name = _env("GSD_TEST_DOCKET_NAME", "gsd-compat-jobs-restart-test")

    redelivery_ms = int(_env("GSD_TEST_REDELIVERY_TIMEOUT_MS", "500"))
    fastmcp.settings.docket.redelivery_timeout = timedelta(milliseconds=max(50, redelivery_ms))
    fastmcp.settings.docket.reconnection_delay = timedelta(milliseconds=50)


def _identity_from_headers() -> Identity:
    from fastmcp.server.dependencies import get_http_headers

    headers = get_http_headers()
    tenant_id = str(headers.get("x-gsd-test-tenant") or "tA").strip() or "tA"
    subject_id = str(headers.get("x-gsd-test-subject") or "sA").strip() or "sA"
    return Identity(tenant_id=tenant_id, subject_id=subject_id, transport="http")


def _fallback_identity() -> Identity:
    return Identity(
        tenant_id=_env("GSD_TEST_BACKGROUND_TENANT", "tA"),
        subject_id=_env("GSD_TEST_BACKGROUND_SUBJECT", "sA"),
        transport="http",
    )


def _identity_for_current_call() -> Identity:
    try:
        return _identity_from_headers()
    except Exception:  # noqa: BLE001
        return _fallback_identity()


async def _fake_long_web_eval_agent(*_args: Any, **_kwargs: Any) -> list[TextContent]:
    payload = WebEvalAgentPayloadV1(
        version="gsd.web_eval_agent.v1",
        session_id=uuid.uuid4(),
        tool_call_id=uuid.uuid4(),
        url=str(_kwargs.get("url") or "http://example.test"),
        task=str(_kwargs.get("task") or "x"),
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

    deadline = time.time() + float(_env("GSD_TEST_TASK_WORK_S", "1.0"))
    while time.time() < deadline:
        await asyncio.sleep(0.05)

    return [TextContent(type="text", text=json.dumps(payload.model_dump(mode="json")))]


_configure_docket()

from gsd_browser import fastmcp_v2_stdio as entry  # noqa: E402

entry.mcp._resolve_identity_for_current_request = _identity_from_headers  # type: ignore[method-assign]
entry._resolve_identity_for_current_call = _identity_for_current_call  # type: ignore[assignment]
entry.sdk_server.web_eval_agent = _fake_long_web_eval_agent  # type: ignore[assignment]

app = entry.mcp.http_app(transport="streamable-http", stateless_http=True)

