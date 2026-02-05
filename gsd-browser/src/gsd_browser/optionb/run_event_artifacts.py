from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from . import s3_client as s3_client_mod
from .artifact_index import ArtifactWriter, build_record, get_artifact_index_store
from .identity import Identity
from .request_context import get_current_identity
from .s3_client import has_complete_s3_config

logger = logging.getLogger("gsd_browser.optionb.run_event_artifacts")


def build_run_events_s3_key(
    *,
    identity: Identity,
    session_id: str,
    timestamp_ms: int,
    chunk_id: str,
) -> str:
    return (
        f"tenants/{identity.tenant_id}/subjects/{identity.subject_id}/sessions/{session_id}"
        f"/run-events/{int(timestamp_ms)}_{chunk_id}.jsonl"
    )


def _is_uuid4(value: str) -> bool:
    try:
        parsed = uuid.UUID(str(value).strip())
    except (TypeError, ValueError):
        return False
    return parsed.version == 4


def _encode_jsonl(events: list[dict[str, Any]]) -> bytes:
    lines: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        lines.append(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")


async def persist_run_event_chunk(
    *,
    session_id: str,
    events: list[dict[str, Any]],
    identity: Identity | None = None,
) -> None:
    if not has_complete_s3_config():
        return

    identity_value = identity or get_current_identity()
    if identity_value is None:
        return

    session_id_value = str(session_id or "").strip()
    if not session_id_value or not _is_uuid4(session_id_value):
        return

    if not events:
        return

    store = get_artifact_index_store()
    if store.docket_getter() is None:
        return

    # Use newest event timestamp (epoch seconds) as the chunk ordering key.
    newest_ts = 0.0
    chunk_has_error = False
    for event in events:
        if not isinstance(event, dict):
            continue
        ts = event.get("timestamp")
        if isinstance(ts, (int, float)):
            newest_ts = max(newest_ts, float(ts))
        if event.get("has_error") is True:
            chunk_has_error = True

    if newest_ts <= 0:
        newest_ts = time.time()

    created_at_ms = int(newest_ts * 1000)
    artifact_id = str(uuid.uuid4())
    if not _is_uuid4(artifact_id):
        return

    body = _encode_jsonl(events)
    content_type = "application/x-ndjson"
    size_bytes = len(body)

    try:
        s3 = s3_client_mod.get_s3_client()
        s3_key = build_run_events_s3_key(
            identity=identity_value,
            session_id=session_id_value,
            timestamp_ms=created_at_ms,
            chunk_id=artifact_id,
        )
        record = build_record(
            artifact_id=artifact_id,
            artifact_kind="run_event_chunk",
            identity=identity_value,
            session_id=session_id_value,
            created_at_ms=created_at_ms,
            content_type=content_type,
            size_bytes=size_bytes,
            s3_bucket=s3.bucket,
            s3_key=s3_key,
            has_error=chunk_has_error,
        )
        writer = ArtifactWriter(index=store)
        await writer.write(
            record,
            upload=lambda: s3.put_bytes(key=s3_key, body=body, content_type=content_type),
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to persist run-events chunk",
            extra={
                "session_id": session_id_value,
                "tenant_id": identity_value.tenant_id,
                "subject_id": identity_value.subject_id,
            },
        )


async def persist_run_events_from_store(
    run_events: Any,
    *,
    session_id: str,
    identity: Identity | None = None,
    max_events: int = 200,
) -> None:
    get_events = getattr(run_events, "get_events", None)
    if not callable(get_events):
        return
    try:
        events = get_events(
            session_id=session_id,
            last_n=int(max_events),
            event_types=None,
            from_timestamp=None,
            has_error=None,
            include_details=True,
        )
    except Exception:  # noqa: BLE001
        return
    if not isinstance(events, list):
        return
    await persist_run_event_chunk(session_id=session_id, events=events, identity=identity)

