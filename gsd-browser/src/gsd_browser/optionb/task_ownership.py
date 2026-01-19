from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from docket import Docket
from pydantic import BaseModel, Field

from .identity import Identity

TaskOwnershipVersion = Literal["gsd.task_ownership.v1"]


class TaskOwnershipRecord(BaseModel):
    version: TaskOwnershipVersion = Field(default="gsd.task_ownership.v1")
    task_id: str
    tenant_id: str
    subject_id: str
    transport: Literal["stdio", "http"]
    tool_name: str
    created_at_ms: int
    expires_at_ms: int
    session_id: str


def _redis_key(task_id: str) -> str:
    return f"gsd:v1:tasks:{task_id}:owner"


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True, slots=True)
class TaskOwnershipStore:
    docket_getter: Callable[[], Docket | None]

    async def write(self, record: TaskOwnershipRecord) -> None:
        import redis.exceptions

        docket = self.docket_getter()
        if docket is None:
            raise RuntimeError("Docket is required for task ownership persistence")

        payload = json.dumps(
            record.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
        )
        key = _redis_key(record.task_id)

        try:
            async with docket.redis() as redis:
                pipe = redis.pipeline(transaction=True)
                pipe.set(key, payload)
                pipe.pexpireat(key, int(record.expires_at_ms))
                await pipe.execute()
        except redis.exceptions.RedisError as exc:
            raise RuntimeError("Failed to write TaskOwnershipRecord") from exc

    async def get(self, task_id: str) -> TaskOwnershipRecord | None:
        import redis.exceptions

        docket = self.docket_getter()
        if docket is None:
            raise RuntimeError("Docket is required for task ownership lookup")

        key = _redis_key(task_id)
        try:
            async with docket.redis() as redis:
                raw = await redis.get(key)
        except redis.exceptions.RedisError as exc:
            raise RuntimeError("Failed to read TaskOwnershipRecord") from exc

        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            return None
        try:
            return TaskOwnershipRecord.model_validate_json(raw)
        except Exception:
            return None

    async def require_owner(
        self, task_id: str, identity: Identity
    ) -> TaskOwnershipRecord | None:
        record = await self.get(task_id)
        if record is None:
            return None
        if record.tenant_id != identity.tenant_id or record.subject_id != identity.subject_id:
            return None
        return record


_store: TaskOwnershipStore | None = None


def get_task_ownership_store() -> TaskOwnershipStore:
    global _store
    if _store is not None:
        return _store

    from fastmcp.server.dependencies import _current_docket

    def get_docket() -> Docket | None:
        return _current_docket.get()

    _store = TaskOwnershipStore(docket_getter=get_docket)
    return _store


def build_record(
    *,
    task_id: str,
    tool_name: str,
    identity: Identity,
    session_id: str,
    ttl_ms: int,
    created_at_ms: int | None = None,
) -> TaskOwnershipRecord:
    created = _now_ms() if created_at_ms is None else int(created_at_ms)
    ttl_ms_value = max(0, int(ttl_ms))
    expires = created + ttl_ms_value
    return TaskOwnershipRecord(
        task_id=task_id,
        tenant_id=identity.tenant_id,
        subject_id=identity.subject_id,
        transport=identity.transport,
        tool_name=tool_name,
        created_at_ms=created,
        expires_at_ms=expires,
        session_id=session_id,
    )
