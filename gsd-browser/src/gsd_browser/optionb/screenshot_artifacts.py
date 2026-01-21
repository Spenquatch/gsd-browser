from __future__ import annotations

import logging
import uuid

from ..screenshot_manager import Screenshot
from . import s3_client as s3_client_mod
from .artifact_index import ArtifactWriter, build_record, get_artifact_index_store
from .identity import Identity
from .request_context import get_current_identity
from .s3_client import has_complete_s3_config

logger = logging.getLogger("gsd_browser.optionb.screenshot_artifacts")


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
    if not has_complete_s3_config():
        return

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
    if store.docket_getter() is None:
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
        writer = ArtifactWriter(index=store)
        await writer.write(
            record,
            upload=lambda: s3.put_bytes(
                key=s3_key,
                body=shot.image_bytes or b"",
                content_type=content_type,
            ),
        )
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
