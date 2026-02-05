from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal

from docket import Docket
from pydantic import BaseModel, Field

from .identity import Identity

logger = logging.getLogger("gsd_browser.optionb.artifact_index")

ArtifactIndexVersion = Literal["gsd.artifact_index.v1"]
ArtifactState = Literal["pending", "ready"]
ArtifactKind = Literal["screenshot", "run_event_chunk"]
ScreenshotType = Literal["agent_step", "stream_sample"] | None

_META_KEY_PREFIX = "gsd:v1:artifacts:"
_CLEANUP_LOCK_KEY = "gsd:v1:maintenance:cleanup:lock"
_PENDING_ORPHAN_THRESHOLD_MS = 10 * 60 * 1000


class ArtifactIndexRecord(BaseModel):
    version: ArtifactIndexVersion = Field(default="gsd.artifact_index.v1")
    state: ArtifactState
    artifact_id: str
    artifact_kind: ArtifactKind
    tenant_id: str
    subject_id: str
    session_id: str
    created_at_ms: int
    content_type: str
    size_bytes: int
    has_error: bool = False
    screenshot_type: ScreenshotType = None
    step: int | None = None
    page_url: str | None = None
    s3_bucket: str
    s3_key: str
    sha256_hex: str | None = None


def _require_uuid(value: str, *, name: str) -> str:
    raw = str(value).strip()
    try:
        parsed = uuid.UUID(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a UUID string") from exc
    if parsed.version != 4:
        raise ValueError(f"{name} must be a UUIDv4 string")
    return raw


def _meta_key(artifact_id: str) -> str:
    return f"{_META_KEY_PREFIX}{artifact_id}:meta"


def _session_zset_key(
    *, tenant_id: str, subject_id: str, session_id: str, kind: ArtifactKind
) -> str:
    suffix = "screenshots:z" if kind == "screenshot" else "run_events:z"
    return (
        f"gsd:v1:tenants:{tenant_id}:subjects:{subject_id}:sessions:{session_id}:{suffix}"
    )


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


def _cleanup_interval_seconds() -> int:
    raw = str(os.environ.get("GSD_CLEANUP_INTERVAL_S", "")).strip()
    return int(raw) if raw else 300


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True, slots=True)
class ArtifactIndexStore:
    docket_getter: Callable[[], Docket | None]

    async def write_meta(self, record: ArtifactIndexRecord, *, expires_at_ms: int) -> None:
        import redis.exceptions

        docket = self.docket_getter()
        if docket is None:
            raise RuntimeError("Docket is required for artifact indexing")

        key = _meta_key(record.artifact_id)
        payload = json.dumps(record.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)
        try:
            async with docket.redis() as redis:
                pipe = redis.pipeline(transaction=True)
                pipe.set(key, payload)
                pipe.pexpireat(key, int(expires_at_ms))
                await pipe.execute()
        except redis.exceptions.RedisError as exc:
            raise RuntimeError("Failed to write ArtifactIndexRecord") from exc

    async def get_meta(self, artifact_id: str) -> ArtifactIndexRecord | None:
        import redis.exceptions

        docket = self.docket_getter()
        if docket is None:
            raise RuntimeError("Docket is required for artifact indexing")

        key = _meta_key(artifact_id)
        try:
            async with docket.redis() as redis:
                raw = await redis.get(key)
        except redis.exceptions.RedisError as exc:
            raise RuntimeError("Failed to read ArtifactIndexRecord") from exc

        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            return None
        try:
            return ArtifactIndexRecord.model_validate_json(raw)
        except Exception:
            return None

    async def delete_meta(self, artifact_id: str) -> None:
        import redis.exceptions

        docket = self.docket_getter()
        if docket is None:
            raise RuntimeError("Docket is required for artifact indexing")
        try:
            async with docket.redis() as redis:
                await redis.delete(_meta_key(artifact_id))
        except redis.exceptions.RedisError as exc:
            raise RuntimeError("Failed to delete ArtifactIndexRecord") from exc

    async def add_to_session_zset(
        self,
        *,
        artifact_id: str,
        tenant_id: str,
        subject_id: str,
        session_id: str,
        kind: ArtifactKind,
        timestamp_ms: int,
    ) -> None:
        import redis.exceptions

        docket = self.docket_getter()
        if docket is None:
            raise RuntimeError("Docket is required for artifact indexing")
        key = _session_zset_key(
            tenant_id=tenant_id, subject_id=subject_id, session_id=session_id, kind=kind
        )
        try:
            async with docket.redis() as redis:
                await redis.zadd(key, {artifact_id: int(timestamp_ms)})
        except redis.exceptions.RedisError as exc:
            raise RuntimeError("Failed to update artifact session zset") from exc

    async def remove_from_session_zset(
        self,
        *,
        artifact_id: str,
        tenant_id: str,
        subject_id: str,
        session_id: str,
        kind: ArtifactKind,
    ) -> None:
        import redis.exceptions

        docket = self.docket_getter()
        if docket is None:
            raise RuntimeError("Docket is required for artifact indexing")
        key = _session_zset_key(
            tenant_id=tenant_id, subject_id=subject_id, session_id=session_id, kind=kind
        )
        try:
            async with docket.redis() as redis:
                await redis.zrem(key, artifact_id)
        except redis.exceptions.RedisError as exc:
            raise RuntimeError("Failed to update artifact session zset") from exc

    async def finalize_ready(self, record: ArtifactIndexRecord, *, expires_at_ms: int) -> None:
        import redis.exceptions

        docket = self.docket_getter()
        if docket is None:
            raise RuntimeError("Docket is required for artifact indexing")

        ready = record.model_copy(update={"state": "ready"})
        meta_key = _meta_key(ready.artifact_id)
        zset_key = _session_zset_key(
            tenant_id=ready.tenant_id,
            subject_id=ready.subject_id,
            session_id=ready.session_id,
            kind=ready.artifact_kind,
        )
        payload = json.dumps(ready.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)
        try:
            async with docket.redis() as redis:
                pipe = redis.pipeline(transaction=True)
                pipe.set(meta_key, payload)
                pipe.pexpireat(meta_key, int(expires_at_ms))
                pipe.zadd(zset_key, {ready.artifact_id: int(ready.created_at_ms)})
                await pipe.execute()
        except redis.exceptions.RedisError as exc:
            raise RuntimeError("Failed to finalize artifact index record") from exc


@dataclass(frozen=True, slots=True)
class ArtifactWriter:
    index: ArtifactIndexStore
    now_ms: Callable[[], int] = _now_ms

    async def write(
        self,
        record: ArtifactIndexRecord,
        *,
        upload: Callable[[], object],
    ) -> None:
        import inspect

        artifact_id = _require_uuid(record.artifact_id, name="artifact_id")
        _ = _require_uuid(record.session_id, name="session_id")
        retention_ms = int(_retention_seconds() * 1000)
        expires_at_ms = int(record.created_at_ms + retention_ms)

        pending = record.model_copy(update={"state": "pending", "artifact_id": artifact_id})
        await self.index.write_meta(pending, expires_at_ms=expires_at_ms)

        try:
            result = upload()
            if inspect.isawaitable(result):
                await result
        except Exception:  # noqa: BLE001
            await self.index.delete_meta(artifact_id)
            raise

        try:
            await self.index.finalize_ready(pending, expires_at_ms=expires_at_ms)
        except Exception:  # noqa: BLE001
            logger.warning(
                "audit.artifact_finalize_failed",
                extra={
                    "artifact_id": artifact_id,
                    "tenant_id": pending.tenant_id,
                    "subject_id": pending.subject_id,
                    "session_id": pending.session_id,
                    "s3_bucket": pending.s3_bucket,
                    "s3_key": pending.s3_key,
                },
            )
            try:
                await self.index.write_meta(pending, expires_at_ms=expires_at_ms)
                await self.index.remove_from_session_zset(
                    artifact_id=artifact_id,
                    tenant_id=pending.tenant_id,
                    subject_id=pending.subject_id,
                    session_id=pending.session_id,
                    kind=pending.artifact_kind,
                )
            except Exception:  # noqa: BLE001
                pass
            # Leave pending; cleanup will treat old pending as orphaned.


@dataclass(frozen=True, slots=True)
class CleanupRunner:
    index: ArtifactIndexStore
    delete_s3: Callable[[str, str], None]
    now_ms: Callable[[], int] = _now_ms

    async def run_once(self) -> bool:
        docket = self.index.docket_getter()
        if docket is None:
            raise RuntimeError("Docket is required for artifact cleanup")
        lease_ms = int(_cleanup_interval_seconds() * 1000 - 5000)
        if lease_ms < 10000:
            lease_ms = 10000

        async with docket.redis() as redis:
            token = str(uuid.uuid4())
            acquired = await redis.set(_CLEANUP_LOCK_KEY, token, nx=True, px=lease_ms)
            if not acquired:
                return False

        await self._cleanup_meta_keys()
        await self._cleanup_zsets_without_meta()
        return True

    async def _scan_keys(self, pattern: str, *, count: int = 200) -> Iterable[str]:
        docket = self.index.docket_getter()
        if docket is None:
            return []
        cursor: int = 0
        keys: list[str] = []
        async with docket.redis() as redis:
            while True:
                cursor, batch = await redis.scan(cursor=cursor, match=pattern, count=count)
                for item in batch:
                    if isinstance(item, bytes):
                        keys.append(item.decode("utf-8"))
                    else:
                        keys.append(str(item))
                if int(cursor) == 0:
                    break
        return keys

    async def _cleanup_meta_keys(self) -> None:
        now_ms = int(self.now_ms())
        retention_ms = int(_retention_seconds() * 1000)
        meta_keys = await self._scan_keys(f"{_META_KEY_PREFIX}*:meta")
        for key in meta_keys:
            try:
                artifact_id = key[len(_META_KEY_PREFIX) :].split(":", 1)[0]
            except Exception:
                continue
            record = await self.index.get_meta(artifact_id)
            if record is None:
                continue

            age_ms = now_ms - int(record.created_at_ms)
            if record.state == "pending":
                if age_ms < _PENDING_ORPHAN_THRESHOLD_MS:
                    continue
                if not self._delete_blob(record):
                    continue
                await self.index.delete_meta(record.artifact_id)
                await self.index.remove_from_session_zset(
                    artifact_id=record.artifact_id,
                    tenant_id=record.tenant_id,
                    subject_id=record.subject_id,
                    session_id=record.session_id,
                    kind=record.artifact_kind,
                )
                continue

            if record.state == "ready" and age_ms >= retention_ms:
                if not self._delete_blob(record):
                    continue
                await self.index.delete_meta(record.artifact_id)
                await self.index.remove_from_session_zset(
                    artifact_id=record.artifact_id,
                    tenant_id=record.tenant_id,
                    subject_id=record.subject_id,
                    session_id=record.session_id,
                    kind=record.artifact_kind,
                )

    def _delete_blob(self, record: ArtifactIndexRecord) -> bool:
        try:
            self.delete_s3(record.s3_bucket, record.s3_key)
        except Exception:  # noqa: BLE001
            return False
        return True

    async def _cleanup_zsets_without_meta(self) -> None:
        docket = self.index.docket_getter()
        if docket is None:
            return
        patterns = (
            "gsd:v1:tenants:*:subjects:*:sessions:*:screenshots:z",
            "gsd:v1:tenants:*:subjects:*:sessions:*:run_events:z",
        )
        for pattern in patterns:
            for zset_key in await self._scan_keys(pattern):
                async with docket.redis() as redis:
                    members = await redis.zrange(zset_key, 0, -1)
                for member in members:
                    artifact_id = (
                        member.decode("utf-8") if isinstance(member, bytes) else str(member)
                    )
                    if await self.index.get_meta(artifact_id) is None:
                        async with docket.redis() as redis:
                            await redis.zrem(zset_key, artifact_id)


def get_artifact_index_store() -> ArtifactIndexStore:
    from fastmcp.server.dependencies import _current_docket

    def get_docket() -> Docket | None:
        return _current_docket.get()

    return ArtifactIndexStore(docket_getter=get_docket)


def build_record(
    *,
    artifact_id: str,
    artifact_kind: ArtifactKind,
    identity: Identity,
    session_id: str,
    created_at_ms: int,
    content_type: str,
    size_bytes: int,
    s3_bucket: str,
    s3_key: str,
    has_error: bool = False,
    screenshot_type: ScreenshotType = None,
    step: int | None = None,
    page_url: str | None = None,
    sha256_hex: str | None = None,
) -> ArtifactIndexRecord:
    _ = _require_uuid(artifact_id, name="artifact_id")
    _ = _require_uuid(session_id, name="session_id")
    return ArtifactIndexRecord(
        state="pending",
        artifact_id=artifact_id,
        artifact_kind=artifact_kind,
        tenant_id=identity.tenant_id,
        subject_id=identity.subject_id,
        session_id=session_id,
        created_at_ms=int(created_at_ms),
        content_type=str(content_type),
        size_bytes=int(size_bytes),
        has_error=bool(has_error),
        screenshot_type=screenshot_type,
        step=step,
        page_url=page_url,
        s3_bucket=str(s3_bucket),
        s3_key=str(s3_key),
        sha256_hex=sha256_hex,
    )
