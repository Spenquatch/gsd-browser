from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from docket import Docket
from docket.execution import ExecutionState
from fastmcp.server.tasks.keys import build_task_key
from pydantic import BaseModel

from .identity import Identity
from .job_store import JobRecord, JobStore

OpsJobState = Literal["queued", "running", "completed", "failed", "cancelled"]
OpsJobTransport = Literal["stdio", "http"]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ms_to_datetime(value_ms: int) -> datetime:
    return datetime.fromtimestamp(value_ms / 1000.0, tz=UTC)


def _truncate(value: str, *, max_len: int) -> str:
    text = str(value or "")
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


class OpsJobsServiceError(ValueError):
    def __init__(self, *, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _parse_uuid4(value: str, *, name: str) -> str:
    try:
        parsed = uuid.UUID(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise OpsJobsServiceError(
            code="invalid_job_id",
            message=f"{name} must be a UUID string",
            details={},
        ) from exc
    if parsed.version != 4:
        raise OpsJobsServiceError(
            code="invalid_job_id",
            message=f"{name} must be a UUIDv4 string",
            details={},
        )
    return str(parsed)


def _job_state_from_execution_state(state: ExecutionState) -> OpsJobState:
    if state == ExecutionState.RUNNING:
        return "running"
    if state == ExecutionState.COMPLETED:
        return "completed"
    if state == ExecutionState.FAILED:
        return "failed"
    if state == ExecutionState.CANCELLED:
        return "cancelled"
    return "queued"


class OpsJobProgress(BaseModel):
    current: int
    total: int
    percentage: float


_SnapshotTuple = tuple[
    OpsJobState,
    str,
    OpsJobProgress | None,
    datetime | None,
    datetime | None,
    datetime | None,
]


def _progress_from_execution(execution) -> OpsJobProgress | None:  # noqa: ANN001
    try:
        total = int(execution.progress.total)
        current_raw = execution.progress.current
        current = int(current_raw) if current_raw is not None else None
        if current is None or total <= 0:
            return None
        percentage = float(current) / float(total) * 100.0
        return OpsJobProgress(
            current=max(0, current),
            total=max(0, total),
            percentage=max(0.0, min(100.0, percentage)),
        )
    except Exception:  # noqa: BLE001
        return None


class OpsJobSnapshot(BaseModel):
    job_id: str
    task_id: str
    tool_name: str
    state: OpsJobState
    progress_message: str
    progress: OpsJobProgress | None
    session_id: str
    created_at: datetime
    started_at: datetime | None
    updated_at: datetime | None
    finished_at: datetime | None
    expires_at: datetime


class OpsAdminJobSnapshot(OpsJobSnapshot):
    tenant_id: str
    subject_id: str
    transport: OpsJobTransport


class OpsJobGetResponse(BaseModel):
    job: OpsJobSnapshot


class OpsAdminJobGetResponse(BaseModel):
    job: OpsAdminJobSnapshot


@dataclass(frozen=True, slots=True)
class OpsJobsService:
    docket_getter: Callable[[], Docket | None]
    now_ms: Callable[[], int] = _now_ms

    def _require_docket(self) -> Docket:
        docket = self.docket_getter()
        if docket is None:
            raise RuntimeError("Docket is required for ops job inspection")
        return docket

    def _job_store(self) -> JobStore:
        return JobStore(docket_getter=self.docket_getter)

    async def _snapshot_for_record(self, record: JobRecord) -> _SnapshotTuple:
        docket = self._require_docket()
        task_key = build_task_key(record.session_id, record.task_id, "tool", record.tool_name)
        execution = await docket.get_execution(task_key)
        if execution is None:
            return "queued", "", None, None, None, None

        await execution.sync()

        state = _job_state_from_execution_state(execution.state)
        progress_message = _truncate(execution.progress.message or "", max_len=2000)
        progress = _progress_from_execution(execution)

        started_at = execution.started_at.astimezone(UTC) if execution.started_at else None
        finished_at = execution.completed_at.astimezone(UTC) if execution.completed_at else None

        updated_at: datetime | None = None
        if execution.progress.updated_at is not None:
            updated_at = execution.progress.updated_at.astimezone(UTC)
        elif finished_at is not None:
            updated_at = finished_at
        elif started_at is not None:
            updated_at = started_at

        return state, progress_message, progress, started_at, updated_at, finished_at

    async def get_job(
        self,
        *,
        identity: Identity,
        job_id: str,
    ) -> OpsJobGetResponse | None:
        job_id_value = _parse_uuid4(job_id, name="job_id")
        record = await self._job_store().require_owner(job_id_value, identity)
        if record is None:
            return None

        (
            state,
            progress_message,
            progress,
            started_at,
            updated_at,
            finished_at,
        ) = await self._snapshot_for_record(record)

        return OpsJobGetResponse(
            job=OpsJobSnapshot(
                job_id=record.job_id,
                task_id=record.task_id,
                tool_name=record.tool_name,
                state=state,
                progress_message=progress_message,
                progress=progress,
                session_id=record.session_id,
                created_at=_ms_to_datetime(int(record.created_at_ms)),
                started_at=started_at,
                updated_at=updated_at,
                finished_at=finished_at,
                expires_at=_ms_to_datetime(int(record.expires_at_ms)),
            )
        )

    async def admin_get_job(
        self,
        *,
        job_id: str,
    ) -> OpsAdminJobGetResponse | None:
        job_id_value = _parse_uuid4(job_id, name="job_id")
        record = await self._job_store().get(job_id_value)
        if record is None:
            return None

        (
            state,
            progress_message,
            progress,
            started_at,
            updated_at,
            finished_at,
        ) = await self._snapshot_for_record(record)

        return OpsAdminJobGetResponse(
            job=OpsAdminJobSnapshot(
                job_id=record.job_id,
                task_id=record.task_id,
                tool_name=record.tool_name,
                state=state,
                progress_message=progress_message,
                progress=progress,
                session_id=record.session_id,
                created_at=_ms_to_datetime(int(record.created_at_ms)),
                started_at=started_at,
                updated_at=updated_at,
                finished_at=finished_at,
                expires_at=_ms_to_datetime(int(record.expires_at_ms)),
                tenant_id=record.tenant_id,
                subject_id=record.subject_id,
                transport=record.transport,
            )
        )


_service: OpsJobsService | None = None


def get_ops_jobs_service() -> OpsJobsService:
    global _service
    if _service is not None:
        return _service

    from fastmcp.server.dependencies import _current_docket

    def get_docket() -> Docket | None:
        return _current_docket.get()

    _service = OpsJobsService(docket_getter=get_docket)
    return _service
