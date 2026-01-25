from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from docket import Docket
from pydantic import BaseModel, Field

from .identity import Identity
from .request_context import require_current_identity

JobRecordVersion = Literal["gsd.job_record.v1"]


class JobRecord(BaseModel):
    version: JobRecordVersion = Field(default="gsd.job_record.v1")
    job_id: str
    task_id: str
    tenant_id: str
    subject_id: str
    transport: Literal["stdio", "http"]
    tool_name: str
    created_at_ms: int
    expires_at_ms: int
    session_id: str


def _require_uuid(value: str, *, name: str) -> str:
    raw = str(value).strip()
    try:
        parsed = uuid.UUID(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a UUID string") from exc
    if parsed.version != 4:
        raise ValueError(f"{name} must be a UUIDv4 string")
    return raw


def _redis_key(job_id: str) -> str:
    return f"gsd:v1:jobs:{job_id}:record"


def _deployment_env() -> str:
    env = str(os.environ.get("GSD_DEPLOYMENT_ENV", "dev")).strip().lower() or "dev"
    return env if env in {"dev", "prod"} else "dev"


def _retention_seconds() -> int:
    env = _deployment_env()
    if env == "prod":
        raw = str(os.environ.get("GSD_RETENTION_SECONDS_PROD", "")).strip()
        return int(raw) if raw else 604800
    raw = str(os.environ.get("GSD_RETENTION_SECONDS_DEV", "")).strip()
    return int(raw) if raw else 86400


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True, slots=True)
class JobStore:
    docket_getter: Callable[[], Docket | None]

    async def write(self, record: JobRecord) -> None:
        import redis.exceptions

        docket = self.docket_getter()
        if docket is None:
            raise RuntimeError("Docket is required for job persistence")

        payload = json.dumps(
            record.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
        )
        key = _redis_key(record.job_id)

        try:
            async with docket.redis() as redis:
                pipe = redis.pipeline(transaction=True)
                pipe.set(key, payload)
                pipe.pexpireat(key, int(record.expires_at_ms))
                await pipe.execute()
        except redis.exceptions.RedisError as exc:
            raise RuntimeError("Failed to write JobRecord") from exc

    async def get(self, job_id: str) -> JobRecord | None:
        import redis.exceptions

        docket = self.docket_getter()
        if docket is None:
            raise RuntimeError("Docket is required for job lookup")

        job_id_value = _require_uuid(job_id, name="job_id")
        key = _redis_key(job_id_value)
        try:
            async with docket.redis() as redis:
                raw = await redis.get(key)
        except redis.exceptions.RedisError as exc:
            raise RuntimeError("Failed to read JobRecord") from exc

        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            return None
        try:
            return JobRecord.model_validate_json(raw)
        except Exception:
            return None

    async def require_owner(self, job_id: str, identity: Identity) -> JobRecord | None:
        record = await self.get(job_id)
        if record is None:
            return None
        if record.tenant_id != identity.tenant_id or record.subject_id != identity.subject_id:
            return None
        return record


_store: JobStore | None = None


def get_job_store() -> JobStore:
    global _store
    if _store is not None:
        return _store

    from fastmcp.server.dependencies import _current_docket

    def get_docket() -> Docket | None:
        return _current_docket.get()

    _store = JobStore(docket_getter=get_docket)
    return _store


async def create_job(
    *,
    task_id: str,
    tool_name: str,
    session_id: str,
    identity: Identity | None = None,
    created_at_ms: int | None = None,
) -> JobRecord:
    identity_value = require_current_identity() if identity is None else identity

    task_id_value = _require_uuid(task_id, name="task_id")
    session_id_value = _require_uuid(session_id, name="session_id")

    job_id_value = str(uuid.uuid4())
    created = _now_ms() if created_at_ms is None else int(created_at_ms)
    expires = created + int(_retention_seconds() * 1000)

    record = JobRecord(
        job_id=job_id_value,
        task_id=task_id_value,
        tenant_id=identity_value.tenant_id,
        subject_id=identity_value.subject_id,
        transport=identity_value.transport,
        tool_name=str(tool_name).strip(),
        created_at_ms=created,
        expires_at_ms=expires,
        session_id=session_id_value,
    )

    store = get_job_store()
    await store.write(record)
    return record


async def get_job(job_id: str, *, identity: Identity | None = None) -> JobRecord | None:
    identity_value = require_current_identity() if identity is None else identity
    store = get_job_store()
    return await store.require_owner(job_id, identity_value)

