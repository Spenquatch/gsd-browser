from __future__ import annotations

import logging
import os
import uuid
from urllib.parse import urlparse

from ..screenshot_manager import Screenshot
from . import s3_client as s3_client_mod
from .artifact_index import ArtifactWriter, build_record, get_artifact_index_store
from .identity import Identity
from .request_context import get_current_identity
from .s3_client import has_complete_s3_config

logger = logging.getLogger("gsd_browser.optionb.screenshot_artifacts")
_warned_incompatible_endpoint = False


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


def _endpoint_is_probably_s3_compatible(endpoint_url: str) -> bool:
    parsed = urlparse(str(endpoint_url or ""))
    host = (parsed.netloc or "").lower()
    if host.endswith(".blob.core.windows.net"):
        return False
    return bool(host)


def _redis_blob_key(artifact_id: str) -> str:
    return f"gsd:v1:artifacts:{artifact_id}:blob"


def build_screenshot_s3_key(
    *,
    identity: Identity,
    session_id: str,
    timestamp_ms: int,
    screenshot_id: str,
) -> str:
    return (
        f"tenants/{identity.tenant_id}/subjects/{identity.subject_id}/sessions/{session_id}"
        f"/screenshots/{int(timestamp_ms)}_{screenshot_id}.png"
    )


def _is_uuid4(value: str) -> bool:
    try:
        parsed = uuid.UUID(str(value).strip())
    except (TypeError, ValueError):
        return False
    return parsed.version == 4


async def persist_screenshot(
    shot: Screenshot,
    *,
    identity: Identity | None = None,
) -> None:
    identity_value = identity or get_current_identity()
    if identity_value is None:
        return

    session_id = str(shot.session_id or "").strip()
    if not session_id or not _is_uuid4(session_id):
        return

    artifact_id = str(shot.id or "").strip()
    if not artifact_id or not _is_uuid4(artifact_id):
        return

    if shot.image_bytes is None:
        return

    store = get_artifact_index_store()
    docket = store.docket_getter()
    if docket is None:
        return

    created_at_ms = int(float(shot.timestamp) * 1000)
    screenshot_type = (
        str(shot.screenshot_type).strip().lower()
        if shot.screenshot_type in {"agent_step", "stream_sample"}
        else None
    )
    content_type = str(shot.mime_type or "image/png")
    size_bytes = len(shot.image_bytes)

    try:
        use_s3 = False
        endpoint_url = str(os.environ.get("GSD_S3_ENDPOINT_URL", "")).strip()
        if has_complete_s3_config() and _endpoint_is_probably_s3_compatible(endpoint_url):
            use_s3 = True
        elif has_complete_s3_config() and not _endpoint_is_probably_s3_compatible(endpoint_url):
            global _warned_incompatible_endpoint
            if not _warned_incompatible_endpoint:
                _warned_incompatible_endpoint = True
                logger.warning(
                    "s3_endpoint_incompatible_falling_back_to_redis",
                    extra={"endpoint_url": endpoint_url},
                )

        writer = ArtifactWriter(index=store)
        if use_s3:
            s3 = s3_client_mod.get_s3_client()
            s3_key = build_screenshot_s3_key(
                identity=identity_value,
                session_id=session_id,
                timestamp_ms=created_at_ms,
                screenshot_id=artifact_id,
            )
            record = build_record(
                artifact_id=artifact_id,
                artifact_kind="screenshot",
                identity=identity_value,
                session_id=session_id,
                created_at_ms=created_at_ms,
                content_type=content_type,
                size_bytes=size_bytes,
                s3_bucket=s3.bucket,
                s3_key=s3_key,
                has_error=bool(shot.has_error),
                screenshot_type=screenshot_type,  # type: ignore[arg-type]
                step=shot.step,
                page_url=shot.url,
            )
            await writer.write(
                record,
                upload=lambda: s3.put_bytes(
                    key=s3_key,
                    body=shot.image_bytes or b"",
                    content_type=content_type,
                ),
            )
        else:
            blob_key = _redis_blob_key(artifact_id)
            record = build_record(
                artifact_id=artifact_id,
                artifact_kind="screenshot",
                identity=identity_value,
                session_id=session_id,
                created_at_ms=created_at_ms,
                content_type=content_type,
                size_bytes=size_bytes,
                s3_bucket="redis",
                s3_key=blob_key,
                has_error=bool(shot.has_error),
                screenshot_type=screenshot_type,  # type: ignore[arg-type]
                step=shot.step,
                page_url=shot.url,
            )
            expires_at_ms = int(created_at_ms + _retention_seconds() * 1000)

            async def upload() -> None:
                async with docket.redis() as redis:
                    pipe = redis.pipeline(transaction=True)
                    pipe.set(blob_key, shot.image_bytes or b"")
                    pipe.pexpireat(blob_key, int(expires_at_ms))
                    await pipe.execute()

            await writer.write(record, upload=upload)
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to persist screenshot artifact",
            extra={
                "artifact_id": artifact_id,
                "session_id": session_id,
                "tenant_id": identity_value.tenant_id,
                "subject_id": identity_value.subject_id,
            },
        )
