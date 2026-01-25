from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Literal

from docket.execution import ExecutionState
from fastmcp.server.dependencies import _current_docket
from fastmcp.server.tasks.keys import build_task_key

from ..contracts.v1 import JobGetPayloadV1, JobProgressV1, JobSubmitPayloadV1, OpsErrorPayloadV1
from .job_store import create_job, get_job

logger = logging.getLogger("gsd_browser.optionb.compat_jobs")

CompatToolName = Literal["web_eval_agent", "web_task_agent", "web_task_agent_github"]


def _now_s() -> float:
    return float(time.time())


def _truncate(value: str, *, max_len: int) -> str:
    text = str(value or "")
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _parse_uuid4(value: str, *, name: str) -> uuid.UUID:
    try:
        parsed = uuid.UUID(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a UUID string") from exc
    if parsed.version != 4:
        raise ValueError(f"{name} must be a UUIDv4 string")
    return parsed


def _job_state_from_execution(state: ExecutionState) -> Literal[
    "queued", "running", "completed", "failed", "cancelled"
]:
    if state == ExecutionState.RUNNING:
        return "running"
    if state == ExecutionState.COMPLETED:
        return "completed"
    if state == ExecutionState.FAILED:
        return "failed"
    if state == ExecutionState.CANCELLED:
        return "cancelled"
    return "queued"


async def submit_job(
    *,
    tool_name: CompatToolName,
    arguments: dict[str, Any],
) -> JobSubmitPayloadV1:
    """Submit a compat job for a long tool.

    This schedules work in Docket and persists a durable JobRecord mapping.
    """

    docket = _current_docket.get()
    if docket is None:
        return JobSubmitPayloadV1(
            version="gsd.job_submit.v1",
            job_id=None,
            tool_name=str(tool_name),
            state=None,
            session_id=None,
            created_at=None,
            expires_at=None,
            error=OpsErrorPayloadV1(
                code="backend_unavailable",
                message="Docket is required for compat job submission",
                details=None,
            ),
        )

    # Pre-allocate identifiers so callers can poll immediately and consistently.
    task_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    task_key = build_task_key(session_id, task_id, "tool", tool_name)

    try:
        await docket.add(tool_name, key=task_key)(**(arguments or {}))
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "compat_job_submit_failed",
            extra={"tool_name": tool_name, "task_id": task_id},
        )
        return JobSubmitPayloadV1(
            version="gsd.job_submit.v1",
            job_id=None,
            tool_name=str(tool_name),
            state=None,
            session_id=None,
            created_at=None,
            expires_at=None,
            error=OpsErrorPayloadV1(
                code="submit_failed",
                message="Failed to submit job",
                details={"error": str(exc)},
            ),
        )

    try:
        record = await create_job(
            task_id=task_id,
            tool_name=tool_name,
            session_id=session_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "compat_job_record_persist_failed",
            extra={"tool_name": tool_name, "task_id": task_id},
        )
        try:
            await docket.cancel(task_key)
        except Exception:  # noqa: BLE001
            pass
        return JobSubmitPayloadV1(
            version="gsd.job_submit.v1",
            job_id=None,
            tool_name=str(tool_name),
            state=None,
            session_id=None,
            created_at=None,
            expires_at=None,
            error=OpsErrorPayloadV1(
                code="persist_failed",
                message="Failed to persist job mapping record",
                details={"error": str(exc)},
            ),
        )

    return JobSubmitPayloadV1(
        version="gsd.job_submit.v1",
        job_id=_parse_uuid4(record.job_id, name="job_id"),
        tool_name=record.tool_name,
        state="queued",
        session_id=_parse_uuid4(record.session_id, name="session_id"),
        created_at=float(record.created_at_ms) / 1000.0,
        expires_at=float(record.expires_at_ms) / 1000.0,
        error=None,
    )


async def job_get(*, job_id: str) -> JobGetPayloadV1:
    """Return a state/progress snapshot for a compat job."""

    try:
        job_uuid = _parse_uuid4(job_id, name="job_id")
    except ValueError as exc:
        return JobGetPayloadV1(
            version="gsd.job_get.v1",
            job_id=None,
            found=False,
            tool_name=None,
            state=None,
            progress_message="",
            progress=None,
            session_id=None,
            created_at=None,
            started_at=None,
            updated_at=None,
            finished_at=None,
            expires_at=None,
            error=OpsErrorPayloadV1(code="invalid_job_id", message=str(exc), details=None),
        )

    record = await get_job(str(job_uuid))
    if record is None:
        return JobGetPayloadV1(
            version="gsd.job_get.v1",
            job_id=job_uuid,
            found=False,
            tool_name=None,
            state=None,
            progress_message="",
            progress=None,
            session_id=None,
            created_at=None,
            started_at=None,
            updated_at=None,
            finished_at=None,
            expires_at=None,
            error=None,
        )

    docket = _current_docket.get()
    if docket is None:
        return JobGetPayloadV1(
            version="gsd.job_get.v1",
            job_id=job_uuid,
            found=True,
            tool_name=record.tool_name,
            state=None,
            progress_message="",
            progress=None,
            session_id=_parse_uuid4(record.session_id, name="session_id"),
            created_at=float(record.created_at_ms) / 1000.0,
            started_at=None,
            updated_at=None,
            finished_at=None,
            expires_at=float(record.expires_at_ms) / 1000.0,
            error=OpsErrorPayloadV1(
                code="backend_unavailable",
                message="Docket is required for compat job lookup",
                details=None,
            ),
        )

    task_key = build_task_key(record.session_id, record.task_id, "tool", record.tool_name)
    execution = await docket.get_execution(task_key)
    if execution is None:
        return JobGetPayloadV1(
            version="gsd.job_get.v1",
            job_id=job_uuid,
            found=True,
            tool_name=record.tool_name,
            state=None,
            progress_message="",
            progress=None,
            session_id=_parse_uuid4(record.session_id, name="session_id"),
            created_at=float(record.created_at_ms) / 1000.0,
            started_at=None,
            updated_at=None,
            finished_at=None,
            expires_at=float(record.expires_at_ms) / 1000.0,
            error=OpsErrorPayloadV1(
                code="execution_not_found",
                message="Job execution not found",
                details=None,
            ),
        )

    await execution.sync()

    progress_message = _truncate(execution.progress.message or "", max_len=2000)
    progress_payload: JobProgressV1 | None = None
    try:
        total = int(execution.progress.total)
        current_raw = execution.progress.current
        current = int(current_raw) if current_raw is not None else None
        if current is not None and total > 0:
            percentage = float(current) / float(total) * 100.0
            progress_payload = JobProgressV1(
                current=max(0, current),
                total=max(0, total),
                percentage=max(0.0, min(100.0, percentage)),
            )
    except Exception:  # noqa: BLE001
        progress_payload = None

    started_at = execution.started_at.timestamp() if execution.started_at is not None else None
    finished_at = (
        execution.completed_at.timestamp() if execution.completed_at is not None else None
    )
    updated_at: float | None = None
    if execution.progress.updated_at is not None:
        updated_at = execution.progress.updated_at.timestamp()
    elif finished_at is not None:
        updated_at = finished_at
    elif started_at is not None:
        updated_at = started_at
    else:
        updated_at = _now_s()

    return JobGetPayloadV1(
        version="gsd.job_get.v1",
        job_id=job_uuid,
        found=True,
        tool_name=record.tool_name,
        state=_job_state_from_execution(execution.state),
        progress_message=progress_message,
        progress=progress_payload,
        session_id=_parse_uuid4(record.session_id, name="session_id"),
        created_at=float(record.created_at_ms) / 1000.0,
        started_at=started_at,
        updated_at=updated_at,
        finished_at=finished_at,
        expires_at=float(record.expires_at_ms) / 1000.0,
        error=None,
    )

