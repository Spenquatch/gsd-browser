from __future__ import annotations

import asyncio
import json
import uuid

from docket import Docket
from fastmcp.server.dependencies import _current_docket
from mcp.types import TextContent

from gsd_browser.contracts.v1 import JobCancelPayloadV1, JobGetPayloadV1
from gsd_browser.optionb.compat_jobs import job_cancel, job_get, submit_job
from gsd_browser.optionb.identity import STDIO_IDENTITY, Identity
from gsd_browser.optionb.request_context import identity_scope


def test_compat_jobs_job_cancel_is_non_enumerable_and_cancels_owned_job() -> None:
    async def web_eval_agent(url: str, task: str) -> list[TextContent]:
        _ = (url, task)
        await asyncio.sleep(1)
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "version": "gsd.web_eval_agent.v1",
                        "session_id": str(uuid.uuid4()),
                        "tool_call_id": str(uuid.uuid4()),
                        "status": "success",
                        "result": None,
                        "summary": "ok",
                    }
                ),
            )
        ]

    async def run() -> None:
        async with Docket(
            name="gsd-compat-jobs-cancel", url="memory://compat-jobs-cancel"
        ) as docket:
            docket.register(web_eval_agent, names=["web_eval_agent"])

            token = _current_docket.set(docket)
            try:
                with identity_scope(STDIO_IDENTITY):
                    submit_payload = await submit_job(
                        tool_name="web_eval_agent",
                        arguments={"url": "http://example.test", "task": "slow"},
                    )
                    assert submit_payload.job_id is not None

                    cancelled = await job_cancel(job_id=str(submit_payload.job_id))
                    cancelled_payload = JobCancelPayloadV1.model_validate(
                        cancelled.model_dump(mode="json")
                    )
                    assert cancelled_payload.version == "gsd.job_cancel.v1"
                    assert cancelled_payload.found is True

                    # Cancellation is cooperative; allow a tiny window for Docket to update state.
                    final_state = cancelled_payload.state
                    for _ in range(50):
                        if final_state == "cancelled":
                            break
                        snapshot = await job_get(job_id=str(submit_payload.job_id))
                        snapshot_payload = JobGetPayloadV1.model_validate(
                            snapshot.model_dump(mode="json")
                        )
                        final_state = snapshot_payload.state
                        await asyncio.sleep(0.01)
                    assert final_state == "cancelled"

                other = Identity(tenant_id="other", subject_id="other", transport="stdio")
                with identity_scope(other):
                    denied = await job_cancel(job_id=str(submit_payload.job_id))
                    denied_payload = JobCancelPayloadV1.model_validate(
                        denied.model_dump(mode="json")
                    )
                    assert denied_payload.found is False
                    assert denied_payload.error is None
                    assert denied_payload.state is None
            finally:
                _current_docket.reset(token)

    asyncio.run(run())
