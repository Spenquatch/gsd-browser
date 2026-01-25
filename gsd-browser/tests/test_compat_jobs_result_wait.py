from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from docket import Docket
from docket.worker import Worker
from fastmcp.server.dependencies import _current_docket
from mcp.types import TextContent

from gsd_browser.contracts.v1 import (
    JobResultNotReadyPayloadV1,
    JobWaitTimeoutPayloadV1,
    WebEvalAgentPayloadV1,
)
from gsd_browser.optionb.compat_jobs import job_result, job_wait, submit_job
from gsd_browser.optionb.identity import STDIO_IDENTITY
from gsd_browser.optionb.request_context import identity_scope


def _web_eval_agent_payload(*, url: str, task: str) -> dict:
    return {
        "version": "gsd.web_eval_agent.v1",
        "session_id": str(uuid.uuid4()),
        "tool_call_id": str(uuid.uuid4()),
        "url": url,
        "task": task,
        "mode": None,
        "requested_mode": None,
        "status": "success",
        "result": None,
        "summary": "ok",
        "page": {"url": None, "title": None},
        "errors_top": [],
        "timeouts": {
            "budget_s": None,
            "step_timeout_s": None,
            "max_steps": None,
            "timed_out": False,
        },
        "warnings": [],
        "artifacts": {"screenshots": 0, "stream_samples": 0, "run_events": 0},
        "next_actions": [],
    }


def test_compat_jobs_job_result_and_job_wait_behave_per_adr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GSD_DEPLOYMENT_ENV", "dev")
    monkeypatch.setenv("GSD_RETENTION_SECONDS_DEV", "60")

    async def web_eval_agent(url: str, task: str) -> list[TextContent]:
        # Ensure `job_result` returns not-ready initially, and `job_wait` can complete quickly.
        await asyncio.sleep(0.6 if task == "slow" else 0.2)
        payload = _web_eval_agent_payload(url=url, task=task)
        return [TextContent(type="text", text=json.dumps(payload))]

    async def run() -> None:
        async with Docket(name="gsd-compat-jobs", url="memory://compat-jobs") as docket:
            docket.register(web_eval_agent, names=["web_eval_agent"])

            async with Worker(docket, concurrency=1) as worker:
                worker_task = asyncio.create_task(worker.run_forever())
                try:
                    token = _current_docket.set(docket)
                    try:
                        with identity_scope(STDIO_IDENTITY):
                            submit_payload = await submit_job(
                                tool_name="web_eval_agent",
                                arguments={"url": "http://example.test", "task": "slow"},
                            )
                            assert submit_payload.job_id is not None

                            not_ready = await job_result(job_id=str(submit_payload.job_id))
                            not_ready_payload = JobResultNotReadyPayloadV1.model_validate(
                                not_ready.model_dump(mode="json")
                            )
                            assert not_ready_payload.version == "gsd.job_result.not_ready.v1"
                            assert not_ready_payload.found is True
                            assert not_ready_payload.state in {"queued", "running"}
                            assert not_ready_payload.error is not None
                            assert not_ready_payload.error.code == "NOT_READY"

                            final = await job_wait(
                                job_id=str(submit_payload.job_id),
                                max_wait_s=3,
                                poll_interval_s=0.5,
                            )
                            final_payload = WebEvalAgentPayloadV1.model_validate(final)
                            assert final_payload.version == "gsd.web_eval_agent.v1"

                            submit_payload = await submit_job(
                                tool_name="web_eval_agent",
                                arguments={"url": "http://example.test", "task": "slow"},
                            )
                            assert submit_payload.job_id is not None

                            timeout = await job_wait(
                                job_id=str(submit_payload.job_id),
                                max_wait_s=0,
                                poll_interval_s=0.5,
                            )
                            timeout_payload = JobWaitTimeoutPayloadV1.model_validate(
                                timeout.model_dump(mode="json")
                            )
                            assert timeout_payload.version == "gsd.job_wait.timeout.v1"
                            assert timeout_payload.error.code == "TIMEOUT"
                            assert timeout_payload.error.details.max_wait_s == 0
                            assert timeout_payload.state in {"queued", "running"}

                            with pytest.raises(ValueError, match="max_wait_s must be <= 3600"):
                                await job_wait(
                                    job_id=str(submit_payload.job_id),
                                    max_wait_s=3601,
                                    poll_interval_s=0.5,
                                )

                            with pytest.raises(ValueError, match="poll_interval_s must be >= 0.5"):
                                await job_wait(
                                    job_id=str(submit_payload.job_id),
                                    max_wait_s=1,
                                    poll_interval_s=0.1,
                                )
                    finally:
                        _current_docket.reset(token)
                finally:
                    worker_task.cancel()
                    try:
                        await worker_task
                    except asyncio.CancelledError:
                        pass

    asyncio.run(run())
