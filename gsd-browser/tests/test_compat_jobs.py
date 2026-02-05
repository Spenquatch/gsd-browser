from __future__ import annotations

import asyncio
import json
import uuid

import fastmcp
import pytest
from fastmcp import Client
from mcp.types import TextContent

from gsd_browser.contracts.v1 import JobGetPayloadV1, JobSubmitPayloadV1
from gsd_browser.fastmcp_v2_stdio import mcp as v2_mcp


def _configure_memory_docket(monkeypatch: pytest.MonkeyPatch, *, label: str) -> None:
    monkeypatch.setattr(fastmcp.settings.docket, "url", f"memory://{label}")
    monkeypatch.setattr(fastmcp.settings.docket, "name", f"gsd-{label}")


def _parse_json_result(result) -> dict:  # noqa: ANN001
    assert result.content
    assert isinstance(result.content[0], TextContent)
    return json.loads(result.content[0].text)


def test_compat_jobs_submit_and_job_get_schema_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_memory_docket(monkeypatch, label="compat-jobs-submit-get")
    monkeypatch.setenv("GSD_DEPLOYMENT_ENV", "dev")
    monkeypatch.setenv("GSD_RETENTION_SECONDS_DEV", "60")

    async def fake_web_eval_agent(  # noqa: PLR0913
        url: str,
        task: str,
        ctx,  # noqa: ANN001
        headless_browser: bool = False,
        mode: str | None = None,
        budget_s: float | None = None,
        max_steps: int | None = None,
        step_timeout_s: float | None = None,
    ) -> list[TextContent]:
        _ = (url, task, ctx, headless_browser, mode, budget_s, max_steps, step_timeout_s)
        await asyncio.sleep(0.05)
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "status": "success",
                        "session_id": str(uuid.uuid4()),
                        "tool_call_id": str(uuid.uuid4()),
                    }
                ),
            )
        ]

    monkeypatch.setattr(
        "gsd_browser.fastmcp_v2_stdio.sdk_server.web_eval_agent",
        fake_web_eval_agent,
    )

    async def run() -> None:
        async with Client(v2_mcp) as client:
            submit_result = await client.call_tool_mcp(
                name="web_eval_agent_submit",
                arguments={
                    "url": "http://example.test",
                    "task": "noop",
                    "headless_browser": True,
                    "max_steps": 1,
                },
            )
            assert submit_result.isError is False
            submit_payload = JobSubmitPayloadV1.model_validate(_parse_json_result(submit_result))
            assert submit_payload.version == "gsd.job_submit.v1"
            assert submit_payload.job_id is not None
            assert submit_payload.state == "queued"

            get_result = await client.call_tool_mcp(
                name="job_get",
                arguments={"job_id": str(submit_payload.job_id)},
            )
            assert get_result.isError is False
            get_payload = JobGetPayloadV1.model_validate(_parse_json_result(get_result))
            assert get_payload.version == "gsd.job_get.v1"
            assert get_payload.found is True
            assert get_payload.state in {
                "queued",
                "running",
                "completed",
                "failed",
                "cancelled",
                None,
            }
            assert isinstance(get_payload.progress_message, str)

            invalid_result = await client.call_tool_mcp(
                name="job_get",
                arguments={"job_id": "not-a-uuid"},
            )
            assert invalid_result.isError is False
            invalid_payload = JobGetPayloadV1.model_validate(_parse_json_result(invalid_result))
            assert invalid_payload.found is False
            assert invalid_payload.error is not None
            assert invalid_payload.error.code == "invalid_job_id"

    asyncio.run(run())
