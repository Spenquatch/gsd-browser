from __future__ import annotations

import asyncio
import logging
import time
import uuid

import fastmcp
import pytest
from fastmcp import Client

from gsd_browser.optionb.artifact_index import (
    ArtifactIndexRecord,
    ArtifactIndexStore,
    ArtifactWriter,
    CleanupRunner,
    build_record,
)
from gsd_browser.optionb.fastmcp_server import GsdFastMCP
from gsd_browser.optionb.identity import Identity


def _configure_memory_docket(monkeypatch: pytest.MonkeyPatch, *, label: str) -> None:
    monkeypatch.setattr(fastmcp.settings.docket, "url", f"memory://{label}")
    monkeypatch.setattr(fastmcp.settings.docket, "name", f"gsd-{label}")


def _store_for_docket(docket) -> ArtifactIndexStore:  # noqa: ANN001
    return ArtifactIndexStore(docket_getter=lambda: docket)


def _session_zset_key(*, tenant_id: str, subject_id: str, session_id: str, kind: str) -> str:
    suffix = "screenshots:z" if kind == "screenshot" else "run_events:z"
    return f"gsd:v1:tenants:{tenant_id}:subjects:{subject_id}:sessions:{session_id}:{suffix}"


def test_artifact_write_atomicity_step1_failure_does_not_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="artifact-atomicity")
    server = GsdFastMCP("artifact-test", tasks=True)

    async def run() -> None:
        async with Client(server):
            docket = server.docket
            assert docket is not None
            identity = Identity(tenant_id="t", subject_id="s", transport="stdio")

            # Step (1) fails -> MUST NOT upload
            store1 = _store_for_docket(docket)
            writer1 = ArtifactWriter(index=store1)
            now_ms = int(time.time() * 1000)
            record = build_record(
                artifact_id=str(uuid.uuid4()),
                artifact_kind="screenshot",
                identity=identity,
                session_id=str(uuid.uuid4()),
                created_at_ms=now_ms,
                content_type="image/png",
                size_bytes=3,
                s3_bucket="b",
                s3_key="tenants/t/subjects/s/sessions/x/screenshots/1.png",
            )

            uploaded: list[bool] = []

            async def failing_write_meta(
                _self: ArtifactIndexStore,
                _record: ArtifactIndexRecord,
                *,
                expires_at_ms: int,
            ) -> None:
                raise RuntimeError("redis down")

            with monkeypatch.context() as patcher:
                patcher.setattr(ArtifactIndexStore, "write_meta", failing_write_meta)
                with pytest.raises(RuntimeError):
                    await writer1.write(record, upload=lambda: uploaded.append(True))
            assert not uploaded

    asyncio.run(run())


def test_artifact_write_atomicity_step2_failure_deletes_meta_and_zset_not_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="artifact-atomicity-step2")
    server = GsdFastMCP("artifact-test", tasks=True)

    async def run() -> None:
        async with Client(server):
            docket = server.docket
            assert docket is not None
            identity = Identity(tenant_id="t", subject_id="s", transport="stdio")
            now_ms = int(time.time() * 1000)

            store = _store_for_docket(docket)
            writer = ArtifactWriter(index=store)
            record = build_record(
                artifact_id=str(uuid.uuid4()),
                artifact_kind="screenshot",
                identity=identity,
                session_id=str(uuid.uuid4()),
                created_at_ms=now_ms,
                content_type="image/png",
                size_bytes=3,
                s3_bucket="b",
                s3_key="tenants/t/subjects/s/sessions/x/screenshots/2.png",
            )

            def failing_upload() -> None:
                raise RuntimeError("s3 down")

            with pytest.raises(RuntimeError):
                await writer.write(record, upload=failing_upload)

            assert await store.get_meta(record.artifact_id) is None

            zset_key = _session_zset_key(
                tenant_id=record.tenant_id,
                subject_id=record.subject_id,
                session_id=record.session_id,
                kind=record.artifact_kind,
            )
            async with docket.redis() as redis:
                assert await redis.zscore(zset_key, record.artifact_id) is None

    asyncio.run(run())


def test_artifact_write_atomicity_step3_failure_leaves_pending_and_emits_audit_log(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _configure_memory_docket(monkeypatch, label="artifact-atomicity-step3")
    server = GsdFastMCP("artifact-test", tasks=True)

    async def run() -> None:
        async with Client(server):
            docket = server.docket
            assert docket is not None
            identity = Identity(tenant_id="t", subject_id="s", transport="stdio")
            now_ms = int(time.time() * 1000)

            store = _store_for_docket(docket)
            writer = ArtifactWriter(index=store)
            record = build_record(
                artifact_id=str(uuid.uuid4()),
                artifact_kind="screenshot",
                identity=identity,
                session_id=str(uuid.uuid4()),
                created_at_ms=now_ms,
                content_type="image/png",
                size_bytes=3,
                s3_bucket="b",
                s3_key="tenants/t/subjects/s/sessions/x/screenshots/3.png",
            )

            async def failing_finalize(
                _self: ArtifactIndexStore,
                _record: ArtifactIndexRecord,
                *,
                expires_at_ms: int,
            ) -> None:
                raise RuntimeError("redis timeout")

            caplog.set_level(logging.WARNING, logger="gsd_browser.optionb.artifact_index")
            with monkeypatch.context() as patcher:
                patcher.setattr(ArtifactIndexStore, "finalize_ready", failing_finalize)
                await writer.write(record, upload=lambda: None)

            stored = await store.get_meta(record.artifact_id)
            assert stored is not None
            assert stored.state == "pending"
            assert any(
                "audit.artifact_finalize_failed" in log_record.message
                for log_record in caplog.records
            )

            zset_key = _session_zset_key(
                tenant_id=record.tenant_id,
                subject_id=record.subject_id,
                session_id=record.session_id,
                kind=record.artifact_kind,
            )
            async with docket.redis() as redis:
                assert await redis.zscore(zset_key, record.artifact_id) is None

    asyncio.run(run())


def test_cleanup_lock_idempotency_and_retention(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_memory_docket(monkeypatch, label="artifact-cleanup")
    monkeypatch.setenv("GSD_DEPLOYMENT_ENV", "dev")
    monkeypatch.setenv("GSD_RETENTION_SECONDS_DEV", "1")
    monkeypatch.setenv("GSD_CLEANUP_INTERVAL_S", "60")

    server = GsdFastMCP("artifact-test", tasks=True)

    deleted: list[tuple[str, str]] = []

    def delete_s3(bucket: str, key: str) -> None:
        if key.endswith("/fail.png") or key.endswith("fail.png"):
            raise RuntimeError("transient s3 delete failure")
        deleted.append((bucket, key))

    async def run() -> None:
        async with Client(server):
            docket = server.docket
            assert docket is not None
            store = _store_for_docket(docket)
            identity = Identity(tenant_id="t", subject_id="s", transport="stdio")

            now_ms = int(time.time() * 1000)
            runner = CleanupRunner(index=store, delete_s3=delete_s3, now_ms=lambda: now_ms)
            runner2 = CleanupRunner(index=store, delete_s3=delete_s3, now_ms=lambda: now_ms)

            pending_old = build_record(
                artifact_id=str(uuid.uuid4()),
                artifact_kind="screenshot",
                identity=identity,
                session_id=str(uuid.uuid4()),
                created_at_ms=now_ms - (10 * 60 * 1000 + 1),
                content_type="image/png",
                size_bytes=1,
                s3_bucket="b",
                s3_key="tenants/t/subjects/s/sessions/x/screenshots/pending.png",
            )
            await store.write_meta(pending_old, expires_at_ms=now_ms + 60_000)

            ready_old = pending_old.model_copy(
                update={
                    "artifact_id": str(uuid.uuid4()),
                    "state": "ready",
                    "created_at_ms": now_ms - 2_000,
                    "s3_key": "tenants/t/subjects/s/sessions/x/screenshots/ready_old.png",
                }
            )
            await store.write_meta(ready_old, expires_at_ms=now_ms + 60_000)
            await store.add_to_session_zset(
                artifact_id=ready_old.artifact_id,
                tenant_id=ready_old.tenant_id,
                subject_id=ready_old.subject_id,
                session_id=ready_old.session_id,
                kind=ready_old.artifact_kind,
                timestamp_ms=ready_old.created_at_ms,
            )

            ready_recent_without_zset = ready_old.model_copy(
                update={
                    "artifact_id": str(uuid.uuid4()),
                    "state": "ready",
                    "created_at_ms": now_ms - 100,
                    "s3_key": "tenants/t/subjects/s/sessions/x/screenshots/ready_recent.png",
                }
            )
            await store.write_meta(ready_recent_without_zset, expires_at_ms=now_ms + 60_000)

            ready_delete_fails = ready_old.model_copy(
                update={
                    "artifact_id": str(uuid.uuid4()),
                    "state": "ready",
                    "created_at_ms": now_ms - 2_000,
                    "s3_key": "tenants/t/subjects/s/sessions/x/screenshots/fail.png",
                }
            )
            await store.write_meta(ready_delete_fails, expires_at_ms=now_ms + 60_000)
            await store.add_to_session_zset(
                artifact_id=ready_delete_fails.artifact_id,
                tenant_id=ready_delete_fails.tenant_id,
                subject_id=ready_delete_fails.subject_id,
                session_id=ready_delete_fails.session_id,
                kind=ready_delete_fails.artifact_kind,
                timestamp_ms=ready_delete_fails.created_at_ms,
            )

            # Orphan zset member without meta should be removed
            orphan_id = str(uuid.uuid4())
            await store.add_to_session_zset(
                artifact_id=orphan_id,
                tenant_id=ready_old.tenant_id,
                subject_id=ready_old.subject_id,
                session_id=ready_old.session_id,
                kind=ready_old.artifact_kind,
                timestamp_ms=now_ms,
            )

            ran, ran2 = await asyncio.gather(runner.run_once(), runner2.run_once())
            assert sorted((ran, ran2)) == [False, True]

            assert await store.get_meta(pending_old.artifact_id) is None
            assert await store.get_meta(ready_old.artifact_id) is None
            assert await store.get_meta(ready_recent_without_zset.artifact_id) is not None
            assert await store.get_meta(ready_delete_fails.artifact_id) is not None

            assert await store.get_meta(orphan_id) is None

            zset_key = _session_zset_key(
                tenant_id=ready_old.tenant_id,
                subject_id=ready_old.subject_id,
                session_id=ready_old.session_id,
                kind=ready_old.artifact_kind,
            )
            async with docket.redis() as redis:
                assert await redis.zscore(zset_key, orphan_id) is None
                assert await redis.zscore(zset_key, ready_old.artifact_id) is None
                assert await redis.zscore(zset_key, ready_delete_fails.artifact_id) is not None
                assert await redis.exists("gsd:v1:maintenance:cleanup:lock") == 1

            assert sorted(deleted) == sorted(
                [
                    (pending_old.s3_bucket, pending_old.s3_key),
                    (ready_old.s3_bucket, ready_old.s3_key),
                ]
            )

    asyncio.run(run())


def test_cleanup_deletion_routing_by_backend_and_not_found_tolerated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="artifact-cleanup-routing")
    monkeypatch.setenv("GSD_DEPLOYMENT_ENV", "dev")
    monkeypatch.setenv("GSD_RETENTION_SECONDS_DEV", "1")
    monkeypatch.setenv("GSD_CLEANUP_INTERVAL_S", "60")

    server = GsdFastMCP("artifact-test", tasks=True)

    deleted_s3: list[tuple[str, str]] = []
    deleted_azure: list[str] = []
    deleted_redis: list[str] = []

    def delete_s3(bucket: str, key: str) -> None:
        deleted_s3.append((bucket, key))

    def delete_azure(blob_name: str) -> None:
        deleted_azure.append(blob_name)
        raise FileNotFoundError("already deleted")

    async def delete_redis(key: str) -> None:
        deleted_redis.append(key)

    async def run() -> None:
        async with Client(server):
            docket = server.docket
            assert docket is not None
            store = _store_for_docket(docket)
            identity = Identity(tenant_id="t", subject_id="s", transport="stdio")

            now_ms = int(time.time() * 1000)
            runner = CleanupRunner(
                index=store,
                delete_s3=delete_s3,
                delete_azure=delete_azure,
                delete_redis=delete_redis,
                now_ms=lambda: now_ms,
            )

            # Azure
            azure_record = build_record(
                artifact_id=str(uuid.uuid4()),
                artifact_kind="screenshot",
                identity=identity,
                session_id=str(uuid.uuid4()),
                created_at_ms=now_ms - 2_000,
                content_type="image/png",
                size_bytes=1,
                s3_bucket="c",
                s3_key="tenants/t/subjects/s/sessions/x/screenshots/azure.png",
                artifact_backend="azure",
            ).model_copy(update={"state": "ready"})
            await store.write_meta(azure_record, expires_at_ms=now_ms + 60_000)

            # S3
            s3_record = build_record(
                artifact_id=str(uuid.uuid4()),
                artifact_kind="screenshot",
                identity=identity,
                session_id=str(uuid.uuid4()),
                created_at_ms=now_ms - 2_000,
                content_type="image/png",
                size_bytes=1,
                s3_bucket="b",
                s3_key="tenants/t/subjects/s/sessions/x/screenshots/s3.png",
                artifact_backend="s3",
            ).model_copy(update={"state": "ready"})
            await store.write_meta(s3_record, expires_at_ms=now_ms + 60_000)

            # Redis
            redis_record = build_record(
                artifact_id=str(uuid.uuid4()),
                artifact_kind="screenshot",
                identity=identity,
                session_id=str(uuid.uuid4()),
                created_at_ms=now_ms - 2_000,
                content_type="image/png",
                size_bytes=1,
                s3_bucket="redis",
                s3_key=f"gsd:v1:artifacts:{uuid.uuid4()}:blob",
                artifact_backend="redis",
            ).model_copy(update={"state": "ready"})
            await store.write_meta(redis_record, expires_at_ms=now_ms + 60_000)

            # Legacy (no artifact_backend): infer S3.
            legacy_record = build_record(
                artifact_id=str(uuid.uuid4()),
                artifact_kind="screenshot",
                identity=identity,
                session_id=str(uuid.uuid4()),
                created_at_ms=now_ms - 2_000,
                content_type="image/png",
                size_bytes=1,
                s3_bucket="legacy-bucket",
                s3_key="tenants/t/subjects/s/sessions/x/screenshots/legacy.png",
                artifact_backend=None,
            ).model_copy(update={"state": "ready"})
            await store.write_meta(legacy_record, expires_at_ms=now_ms + 60_000)

            ran = await runner.run_once()
            assert ran is True

            assert await store.get_meta(azure_record.artifact_id) is None
            assert await store.get_meta(s3_record.artifact_id) is None
            assert await store.get_meta(redis_record.artifact_id) is None
            assert await store.get_meta(legacy_record.artifact_id) is None

            assert deleted_azure == [str(azure_record.s3_key)]
            assert str(redis_record.s3_key) in deleted_redis
            assert sorted(deleted_s3) == sorted(
                [
                    (str(s3_record.s3_bucket), str(s3_record.s3_key)),
                    (str(legacy_record.s3_bucket), str(legacy_record.s3_key)),
                ]
            )

    asyncio.run(run())
