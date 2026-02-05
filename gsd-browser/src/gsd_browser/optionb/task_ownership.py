from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from docket import Docket
from pydantic import BaseModel, Field

from .identity import Identity

logger = logging.getLogger("gsd_browser.optionb.task_ownership")

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
    worker_id: str = Field(default="")


def _redis_key(task_id: str) -> str:
    return f"gsd:v1:tasks:{task_id}:owner"


def _session_index_key(*, tenant_id: str, subject_id: str) -> str:
    """Key for ZSET of sessions by identity: member=session_id, score=created_at_ms."""
    return f"gsd:v1:tenants:{tenant_id}:subjects:{subject_id}:sessions:z"


def _task_index_key(*, tenant_id: str, subject_id: str, session_id: str) -> str:
    """Key for ZSET of tasks by session: member=task_id, score=created_at_ms."""
    return f"gsd:v1:tenants:{tenant_id}:subjects:{subject_id}:sessions:{session_id}:tasks:z"


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True, slots=True)
class TaskOwnershipStore:
    docket_getter: Callable[[], Docket | None]

    async def write(self, record: TaskOwnershipRecord) -> None:
        """Write task ownership record and update identity-scoped indexes.

        Maintains two secondary indexes for efficient lookups:
        1. Session index: ZSET of sessions per identity (score=created_at_ms)
        2. Task index: ZSET of tasks per session (score=created_at_ms)

        Index expiry uses "max rule": new expiry = max(current_key_expiry, new_member_expiry).
        This prevents accidentally expiring an index that still has newer members.
        """
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
        session_idx_key = _session_index_key(
            tenant_id=record.tenant_id, subject_id=record.subject_id
        )
        task_idx_key = _task_index_key(
            tenant_id=record.tenant_id,
            subject_id=record.subject_id,
            session_id=record.session_id,
        )
        expires_at_ms = int(record.expires_at_ms)
        created_at_ms = int(record.created_at_ms)

        try:
            async with docket.redis() as client:
                # Get current TTLs to apply max rule
                session_idx_ttl = await client.pttl(session_idx_key)
                task_idx_ttl = await client.pttl(task_idx_key)

                # Calculate new expiry using max rule
                now_ms = _now_ms()
                session_idx_current_expiry = (
                    now_ms + session_idx_ttl if session_idx_ttl > 0 else 0
                )
                task_idx_current_expiry = now_ms + task_idx_ttl if task_idx_ttl > 0 else 0

                session_idx_new_expiry = max(session_idx_current_expiry, expires_at_ms)
                task_idx_new_expiry = max(task_idx_current_expiry, expires_at_ms)

                pipe = client.pipeline(transaction=True)
                # Write ownership record
                pipe.set(key, payload)
                pipe.pexpireat(key, expires_at_ms)
                # Update session index (ZADD with score=created_at_ms)
                pipe.zadd(session_idx_key, {record.session_id: created_at_ms})
                pipe.pexpireat(session_idx_key, session_idx_new_expiry)
                # Update task index (ZADD with score=created_at_ms)
                pipe.zadd(task_idx_key, {record.task_id: created_at_ms})
                pipe.pexpireat(task_idx_key, task_idx_new_expiry)
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
            async with docket.redis() as client:
                raw = await client.get(key)
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

    async def list_sessions_by_identity(
        self,
        identity: Identity,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[str], int]:
        """List session IDs for an identity using the indexed ZSET.

        Returns (session_ids, total_count).
        Sessions are ordered by creation time (newest first).
        """
        import redis.exceptions

        docket = self.docket_getter()
        if docket is None:
            raise RuntimeError("Docket is required for session listing")

        session_idx_key = _session_index_key(
            tenant_id=identity.tenant_id, subject_id=identity.subject_id
        )

        try:
            async with docket.redis() as client:
                # Get total count
                total = await client.zcard(session_idx_key)
                if total == 0:
                    return [], 0

                # Get paginated results (newest first via ZREVRANGE)
                start = offset
                end = offset + limit - 1
                members = await client.zrevrange(session_idx_key, start, end)

                session_ids = [
                    m.decode("utf-8") if isinstance(m, bytes) else str(m) for m in members
                ]
                return session_ids, total
        except redis.exceptions.RedisError as exc:
            raise RuntimeError("Failed to list sessions by identity") from exc

    async def list_tasks_by_session(
        self,
        identity: Identity,
        session_id: str,
    ) -> list[str]:
        """List task IDs for a session using the indexed ZSET.

        Returns task_ids ordered by creation time (oldest first).
        """
        import redis.exceptions

        docket = self.docket_getter()
        if docket is None:
            raise RuntimeError("Docket is required for task listing")

        task_idx_key = _task_index_key(
            tenant_id=identity.tenant_id,
            subject_id=identity.subject_id,
            session_id=session_id,
        )

        try:
            async with docket.redis() as client:
                members = await client.zrange(task_idx_key, 0, -1)
                return [m.decode("utf-8") if isinstance(m, bytes) else str(m) for m in members]
        except redis.exceptions.RedisError as exc:
            raise RuntimeError("Failed to list tasks by session") from exc

    async def get_records_for_tasks(
        self, task_ids: list[str]
    ) -> dict[str, TaskOwnershipRecord]:
        """Batch-fetch TaskOwnershipRecords by task IDs using MGET.

        Returns a dict mapping task_id to record (missing/expired tasks omitted).
        """
        import redis.exceptions

        if not task_ids:
            return {}

        docket = self.docket_getter()
        if docket is None:
            raise RuntimeError("Docket is required for batch task lookup")

        keys = [_redis_key(tid) for tid in task_ids]
        now_ms = _now_ms()

        try:
            async with docket.redis() as client:
                raw_values = await client.mget(keys)

            result: dict[str, TaskOwnershipRecord] = {}
            for tid, raw in zip(task_ids, raw_values, strict=False):
                if raw is None:
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                if not isinstance(raw, str):
                    continue
                try:
                    record = TaskOwnershipRecord.model_validate_json(raw)
                except Exception:  # noqa: BLE001
                    continue
                # Skip expired records
                if int(record.expires_at_ms) <= now_ms:
                    continue
                result[tid] = record
            return result
        except redis.exceptions.RedisError as exc:
            raise RuntimeError("Failed to batch-fetch TaskOwnershipRecords") from exc

    async def has_session_index(self, identity: Identity) -> bool:
        """Check if the session index exists (for fallback detection)."""
        import redis.exceptions

        docket = self.docket_getter()
        if docket is None:
            return False

        session_idx_key = _session_index_key(
            tenant_id=identity.tenant_id, subject_id=identity.subject_id
        )

        try:
            async with docket.redis() as client:
                return await client.exists(session_idx_key) > 0
        except redis.exceptions.RedisError:
            return False


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
    worker_id: str = "",
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
        worker_id=worker_id,
    )
