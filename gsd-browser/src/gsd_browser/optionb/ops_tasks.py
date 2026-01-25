from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from docket import Docket
from pydantic import BaseModel, Field

from .identity import Identity
from .task_ownership import TaskOwnershipRecord

OpsTaskStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
OpsTaskTransport = Literal["stdio", "http"]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ms_to_datetime(value_ms: int) -> datetime:
    return datetime.fromtimestamp(value_ms / 1000.0, tz=UTC)


def _parse_rfc3339(value: str) -> datetime | None:
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _parse_duration(value: str) -> timedelta | None:
    raw = value.strip().lower()
    if not raw:
        return None
    unit = raw[-1]
    number = raw[:-1]
    if unit not in {"s", "m", "h", "d"}:
        return None
    try:
        amount = int(number)
    except ValueError:
        return None
    if amount < 0:
        return None
    if unit == "s":
        return timedelta(seconds=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    return timedelta(days=amount)


def _normalize_tool_names(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    parts = [part.strip() for part in raw.split(",")]
    cleaned = [part for part in parts if part]
    if not cleaned:
        return None
    # Keep order stable for cursor binding, but de-dupe case-sensitively.
    seen: set[str] = set()
    out: list[str] = []
    for name in cleaned:
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


class OpsTasksServiceError(ValueError):
    def __init__(self, *, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _invalid_cursor_error() -> OpsTasksServiceError:
    return OpsTasksServiceError(
        code="invalid_cursor",
        message="Cursor does not match query",
        details={"hint": "Do not reuse cursors across filters."},
    )


class OpsTasksListQuery(BaseModel):
    limit: int | None = Field(default=None)
    cursor: str | None = Field(default=None)
    status: OpsTaskStatus | None = Field(default=None)
    tool_name: str | None = Field(default=None)
    since: str | None = Field(default=None)

    def effective_limit(self) -> int:
        if self.limit is None:
            return 100
        value = int(self.limit)
        if value < 1 or value > 1000:
            raise OpsTasksServiceError(
                code="invalid_limit",
                message="Invalid limit",
                details={"max": 1000, "min": 1, "default": 100},
            )
        return value

    def tool_names(self) -> list[str] | None:
        return _normalize_tool_names(self.tool_name)

    def since_datetime(self, *, now: datetime) -> datetime | None:
        if self.since is None:
            return None
        raw = self.since.strip()
        if not raw:
            return None

        dt = _parse_rfc3339(raw)
        if dt is not None:
            return dt

        duration = _parse_duration(raw)
        if duration is not None:
            return now - duration

        raise OpsTasksServiceError(
            code="invalid_since",
            message="Invalid since",
            details={"hint": "Use RFC3339 timestamp or duration like 30m, 7d."},
        )


class OpsAdminTasksListQuery(OpsTasksListQuery):
    tenant_id: str | None = Field(default=None)
    subject_id: str | None = Field(default=None)
    transport: OpsTaskTransport | None = Field(default=None)


class OpsTasksListItem(BaseModel):
    task_id: str
    tool_name: str
    status: OpsTaskStatus
    created_at: datetime
    updated_at: datetime | None
    expires_at: datetime
    session_id: str


class OpsAdminTasksListItem(OpsTasksListItem):
    tenant_id: str
    subject_id: str
    transport: OpsTaskTransport


class OpsTasksListResponse(BaseModel):
    tasks: list[OpsTasksListItem]
    next_cursor: str | None


class OpsAdminTasksListResponse(BaseModel):
    tasks: list[OpsAdminTasksListItem]
    next_cursor: str | None


class _CursorBinding(BaseModel):
    v: Literal[1] = 1
    mode: Literal["identity", "admin"]
    tenant_id: str | None = None
    subject_id: str | None = None
    transport: OpsTaskTransport | None = None
    status: OpsTaskStatus | None = None
    tool_names: list[str] | None = None
    since: str | None = None


class _CursorPayload(BaseModel):
    v: Literal[1] = 1
    binding: _CursorBinding
    last_created_at_ms: int
    last_task_id: str


def _encode_cursor(payload: _CursorPayload) -> str:
    raw = json.dumps(
        payload.model_dump(mode="json"),
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return token


def _decode_cursor(cursor: str) -> _CursorPayload:
    raw = cursor.strip()
    if not raw:
        raise _invalid_cursor_error()
    padding = "=" * (-len(raw) % 4)
    try:
        decoded = base64.urlsafe_b64decode(f"{raw}{padding}".encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
        return _CursorPayload.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        raise _invalid_cursor_error() from exc


def _build_task_key(*, task_id: str, tool_name: str, session_id: str) -> str:
    from fastmcp.server.tasks.keys import build_task_key

    return build_task_key(session_id, task_id, "tool", tool_name)


def _hydrate_status_from_runs_hash(
    *,
    runs_hash: dict[bytes, bytes],
) -> tuple[OpsTaskStatus, datetime | None]:
    raw_state = runs_hash.get(b"state")
    state = raw_state.decode("utf-8") if isinstance(raw_state, (bytes, bytearray)) else ""

    status: OpsTaskStatus
    if state in {"running"}:
        status = "running"
    elif state in {"completed"}:
        status = "completed"
    elif state in {"failed"}:
        status = "failed"
    elif state in {"cancelled"}:
        status = "cancelled"
    else:
        # scheduled/queued/unknown → queued (best-effort)
        status = "queued"

    updated_at: datetime | None = None
    for key in (b"completed_at", b"started_at"):
        raw_dt = runs_hash.get(key)
        if raw_dt is None:
            continue
        try:
            dt = datetime.fromisoformat(raw_dt.decode("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        updated_at = dt.astimezone(UTC)
        break

    return status, updated_at


def _sort_key(record: TaskOwnershipRecord) -> tuple[int, str]:
    return (int(record.created_at_ms), record.task_id)


def _after_cursor(
    *,
    record: TaskOwnershipRecord,
    cursor_created_at_ms: int,
    cursor_task_id: str,
) -> bool:
    created_at_ms = int(record.created_at_ms)
    if created_at_ms < cursor_created_at_ms:
        return True
    if created_at_ms > cursor_created_at_ms:
        return False
    # created_at equal; order is task_id desc, so "after" means strictly less task_id
    return record.task_id < cursor_task_id


@dataclass(frozen=True, slots=True)
class OpsTasksService:
    docket_getter: Callable[[], Docket | None]
    now_ms: Callable[[], int] = _now_ms

    def _require_docket(self) -> Docket:
        docket = self.docket_getter()
        if docket is None:
            raise RuntimeError("Docket is required for ops task listing")
        return docket

    async def _read_all_ownership_records(self) -> list[TaskOwnershipRecord]:
        import redis.exceptions

        docket = self._require_docket()
        pattern = "gsd:v1:tasks:*:owner"
        records: list[TaskOwnershipRecord] = []

        try:
            async with docket.redis() as redis:
                cursor = 0
                while True:
                    cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=250)
                    if keys:
                        raw_values = await redis.mget(keys)
                        for raw in raw_values:
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
                            records.append(record)
                    if cursor == 0:
                        break
        except redis.exceptions.RedisError as exc:
            raise RuntimeError("Failed to list TaskOwnershipRecords") from exc

        return records

    async def list_tasks(
        self,
        *,
        identity: Identity,
        query: OpsTasksListQuery,
    ) -> OpsTasksListResponse:
        limit = query.effective_limit()
        tool_names = query.tool_names()
        now = _ms_to_datetime(self.now_ms())
        since_dt = query.since_datetime(now=now)

        binding = _CursorBinding(
            mode="identity",
            tenant_id=identity.tenant_id,
            subject_id=identity.subject_id,
            status=query.status,
            tool_names=tool_names,
            since=(query.since.strip() if query.since else None),
        )
        cursor_created_at_ms: int | None = None
        cursor_task_id: str | None = None
        if query.cursor:
            decoded = _decode_cursor(query.cursor)
            if decoded.binding != binding:
                raise _invalid_cursor_error()
            cursor_created_at_ms = decoded.last_created_at_ms
            cursor_task_id = decoded.last_task_id

        records = await self._read_all_ownership_records()
        now_ms = self.now_ms()

        filtered: list[TaskOwnershipRecord] = []
        allowed_tool_names = set(tool_names or [])
        for record in records:
            if record.tenant_id != identity.tenant_id or record.subject_id != identity.subject_id:
                continue
            if int(record.expires_at_ms) <= int(now_ms):
                continue
            if tool_names is not None and record.tool_name not in allowed_tool_names:
                continue
            if since_dt is not None and _ms_to_datetime(int(record.created_at_ms)) < since_dt:
                continue
            if cursor_created_at_ms is not None and cursor_task_id is not None:
                if not _after_cursor(
                    record=record,
                    cursor_created_at_ms=cursor_created_at_ms,
                    cursor_task_id=cursor_task_id,
                ):
                    continue
            filtered.append(record)

        filtered.sort(key=_sort_key, reverse=True)

        items: list[OpsTasksListItem] = []
        next_cursor: str | None = None
        last_cursor_created_at_ms: int | None = None
        last_cursor_task_id: str | None = None

        docket = self._require_docket()
        async with docket.redis() as redis:
            for record in filtered:
                status = "queued"
                updated_at: datetime | None = None
                try:
                    task_key = _build_task_key(
                        task_id=record.task_id,
                        tool_name=record.tool_name,
                        session_id=record.session_id,
                    )
                    runs_hash = await redis.hgetall(docket.runs_key(task_key))
                    if runs_hash:
                        status, updated_at = _hydrate_status_from_runs_hash(runs_hash=runs_hash)
                except Exception:  # noqa: BLE001
                    status = "queued"
                    updated_at = None

                if query.status is not None and status != query.status:
                    continue

                items.append(
                    OpsTasksListItem(
                        task_id=record.task_id,
                        tool_name=record.tool_name,
                        status=status,
                        created_at=_ms_to_datetime(int(record.created_at_ms)),
                        updated_at=updated_at,
                        expires_at=_ms_to_datetime(int(record.expires_at_ms)),
                        session_id=record.session_id,
                    )
                )

                if len(items) == limit:
                    last_cursor_created_at_ms = int(record.created_at_ms)
                    last_cursor_task_id = record.task_id

                if len(items) == limit + 1:
                    break

        if len(items) > limit:
            if last_cursor_created_at_ms is None or last_cursor_task_id is None:
                raise RuntimeError("Cursor computation failed")
            next_cursor = _encode_cursor(
                _CursorPayload(
                    binding=binding,
                    last_created_at_ms=last_cursor_created_at_ms,
                    last_task_id=last_cursor_task_id,
                )
            )
            items = items[:limit]

        return OpsTasksListResponse(tasks=items, next_cursor=next_cursor)

    async def admin_list_tasks(self, *, query: OpsAdminTasksListQuery) -> OpsAdminTasksListResponse:
        limit = query.effective_limit()
        tool_names = query.tool_names()
        now = _ms_to_datetime(self.now_ms())
        since_dt = query.since_datetime(now=now)

        binding = _CursorBinding(
            mode="admin",
            tenant_id=query.tenant_id.strip() if query.tenant_id else None,
            subject_id=query.subject_id.strip() if query.subject_id else None,
            transport=query.transport,
            status=query.status,
            tool_names=tool_names,
            since=(query.since.strip() if query.since else None),
        )
        cursor_created_at_ms: int | None = None
        cursor_task_id: str | None = None
        if query.cursor:
            decoded = _decode_cursor(query.cursor)
            if decoded.binding != binding:
                raise _invalid_cursor_error()
            cursor_created_at_ms = decoded.last_created_at_ms
            cursor_task_id = decoded.last_task_id

        records = await self._read_all_ownership_records()
        now_ms = self.now_ms()

        filtered: list[TaskOwnershipRecord] = []
        allowed_tool_names = set(tool_names or [])
        for record in records:
            if int(record.expires_at_ms) <= int(now_ms):
                continue
            if query.tenant_id and record.tenant_id != query.tenant_id:
                continue
            if query.subject_id and record.subject_id != query.subject_id:
                continue
            if query.transport and record.transport != query.transport:
                continue
            if tool_names is not None and record.tool_name not in allowed_tool_names:
                continue
            if since_dt is not None and _ms_to_datetime(int(record.created_at_ms)) < since_dt:
                continue
            if cursor_created_at_ms is not None and cursor_task_id is not None:
                if not _after_cursor(
                    record=record,
                    cursor_created_at_ms=cursor_created_at_ms,
                    cursor_task_id=cursor_task_id,
                ):
                    continue
            filtered.append(record)

        filtered.sort(key=_sort_key, reverse=True)

        items: list[OpsAdminTasksListItem] = []
        next_cursor: str | None = None
        last_cursor_created_at_ms: int | None = None
        last_cursor_task_id: str | None = None

        docket = self._require_docket()
        async with docket.redis() as redis:
            for record in filtered:
                status = "queued"
                updated_at: datetime | None = None
                try:
                    task_key = _build_task_key(
                        task_id=record.task_id,
                        tool_name=record.tool_name,
                        session_id=record.session_id,
                    )
                    runs_hash = await redis.hgetall(docket.runs_key(task_key))
                    if runs_hash:
                        status, updated_at = _hydrate_status_from_runs_hash(runs_hash=runs_hash)
                except Exception:  # noqa: BLE001
                    status = "queued"
                    updated_at = None

                if query.status is not None and status != query.status:
                    continue

                items.append(
                    OpsAdminTasksListItem(
                        task_id=record.task_id,
                        tool_name=record.tool_name,
                        status=status,
                        created_at=_ms_to_datetime(int(record.created_at_ms)),
                        updated_at=updated_at,
                        expires_at=_ms_to_datetime(int(record.expires_at_ms)),
                        session_id=record.session_id,
                        tenant_id=record.tenant_id,
                        subject_id=record.subject_id,
                        transport=record.transport,
                    )
                )

                if len(items) == limit:
                    last_cursor_created_at_ms = int(record.created_at_ms)
                    last_cursor_task_id = record.task_id

                if len(items) == limit + 1:
                    break

        if len(items) > limit:
            if last_cursor_created_at_ms is None or last_cursor_task_id is None:
                raise RuntimeError("Cursor computation failed")
            next_cursor = _encode_cursor(
                _CursorPayload(
                    binding=binding,
                    last_created_at_ms=last_cursor_created_at_ms,
                    last_task_id=last_cursor_task_id,
                )
            )
            items = items[:limit]

        return OpsAdminTasksListResponse(tasks=items, next_cursor=next_cursor)


_service: OpsTasksService | None = None


def get_ops_tasks_service() -> OpsTasksService:
    global _service
    if _service is not None:
        return _service

    from fastmcp.server.dependencies import _current_docket

    def get_docket() -> Docket | None:
        return _current_docket.get()

    _service = OpsTasksService(docket_getter=get_docket)
    return _service
