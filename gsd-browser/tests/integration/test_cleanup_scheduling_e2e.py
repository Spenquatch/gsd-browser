from __future__ import annotations

import asyncio
import time
from uuid import uuid4

import pytest
import redis
from docket import Docket

from gsd_browser.optionb.artifact_index import ArtifactIndexStore, CleanupRunner, build_record
from gsd_browser.optionb.identity import Identity
from gsd_browser.optionb.maintenance import run_cleanup_maintenance_loop


def _redis_ready(url: str) -> bool:
    client = redis.Redis.from_url(url, decode_responses=True)
    try:
        return bool(client.ping())
    except Exception:  # noqa: BLE001
        return False


def test_cleanup_scheduling_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    docket_url = "redis://localhost:6379/0"
    if not _redis_ready(docket_url):
        pytest.skip(
            f"Redis/Valkey not available at {docket_url}. "
            "Start with `docker compose -f docker/compose.redistest.yml up -d`."
        )

    monkeypatch.setenv("GSD_DEPLOYMENT_ENV", "dev")
    monkeypatch.setenv("GSD_RETENTION_SECONDS_DEV", "0")
    monkeypatch.setenv("GSD_CLEANUP_INTERVAL_S", "1")

    docket_name = f"gsd-test-cleanup-{uuid4().hex[:8]}"
    identity = Identity(tenant_id="tenant1", subject_id="subject1", transport="http")
    session_id = str(uuid4())
    artifact_id = str(uuid4())
    created_at_ms = int(time.time() * 1000) - 10_000

    async def run() -> None:
        async with Docket(name=docket_name, url=docket_url) as docket:
            store = ArtifactIndexStore(docket_getter=lambda: docket)

            async with docket.redis() as redis_client:
                await redis_client.delete("gsd:v1:maintenance:cleanup:lock")

            record = build_record(
                artifact_id=artifact_id,
                artifact_kind="screenshot",
                identity=identity,
                session_id=session_id,
                created_at_ms=created_at_ms,
                content_type="image/png",
                size_bytes=123,
                s3_bucket="test-bucket",
                s3_key="test/key.png",
            ).model_copy(update={"state": "ready"})

            expires_at_ms = int(time.time() * 1000) + 60_000
            await store.write_meta(record, expires_at_ms=expires_at_ms)
            await store.add_to_session_zset(
                artifact_id=artifact_id,
                tenant_id=identity.tenant_id,
                subject_id=identity.subject_id,
                session_id=session_id,
                kind="screenshot",
                timestamp_ms=created_at_ms,
            )

            delete_calls = 0

            def delete_s3(_bucket: str, _key: str) -> None:
                nonlocal delete_calls
                delete_calls += 1

            runner_a = CleanupRunner(index=store, delete_s3=delete_s3)
            runner_b = CleanupRunner(index=store, delete_s3=delete_s3)

            loop_a = asyncio.create_task(
                run_cleanup_maintenance_loop(runner_a, interval_seconds=1),
                name="cleanup_loop_a",
            )
            loop_b = asyncio.create_task(
                run_cleanup_maintenance_loop(runner_b, interval_seconds=1),
                name="cleanup_loop_b",
            )
            try:
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline and delete_calls < 1:
                    await asyncio.sleep(0.05)

                assert delete_calls == 1
                assert await store.get_meta(artifact_id) is None

                zset_key = (
                    f"gsd:v1:tenants:{identity.tenant_id}:subjects:{identity.subject_id}:sessions:"
                    f"{session_id}:screenshots:z"
                )
                async with docket.redis() as redis_client:
                    assert await redis_client.zscore(zset_key, artifact_id) is None
            finally:
                loop_a.cancel()
                loop_b.cancel()
                await asyncio.gather(loop_a, loop_b, return_exceptions=True)

    asyncio.run(run())

