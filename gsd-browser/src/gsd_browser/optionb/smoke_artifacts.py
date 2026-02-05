from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import time
import uuid
from typing import Any

from docket import Docket

from ..mcp_server import get_screenshots
from ..screenshot_manager import Screenshot
from .azure_blob_client import has_azure_blob_config
from .identity import Identity
from .request_context import identity_scope
from .screenshot_artifacts import persist_screenshot

_PNG_1X1_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMA"
    "ASsJTYQAAAAASUVORK5CYII="
)
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _env(name: str) -> str:
    return str(os.environ.get(name, "")).strip()


def _validate_png_bytes(data: bytes) -> bool:
    return bool(data.startswith(_PNG_MAGIC))


def _validate_png_base64(data_b64: str) -> bool:
    try:
        raw = base64.b64decode(data_b64, validate=True)
    except Exception:  # noqa: BLE001
        return False
    return _validate_png_bytes(raw)


def _build_identity(*, tenant_id: str, subject_id: str) -> Identity:
    # Keep values short + URL/Redis-safe. Validate loosely; stricter validation exists in
    # identity_from_claims for HTTP-mode JWT.
    tenant = (tenant_id or "").strip() or "smoke"
    subject = (subject_id or "").strip() or "smoke"
    return Identity(tenant_id=tenant, subject_id=subject, transport="http")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="In-container smoke for Option B artifact persistence + retrieval"
    )
    parser.add_argument(
        "--delivery-mode",
        default="inline",
        choices=("inline", "presigned", "both"),
        help="Override GSD_ARTIFACT_DELIVERY_MODE for this process (default: inline).",
    )
    parser.add_argument(
        "--tenant-id",
        default="smoke",
        help="Identity tenant_id used for indexing keys (default: smoke).",
    )
    parser.add_argument(
        "--subject-id",
        default="smoke",
        help="Identity subject_id used for indexing keys (default: smoke).",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Best-effort cleanup: delete blob + index entries after validation.",
    )
    return parser.parse_args(argv)


async def _run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    if not has_azure_blob_config():
        return {
            "ok": False,
            "error": "Azure Blob config missing (GSD_AZURE_STORAGE_ACCOUNT not set).",
        }

    # Make delivery mode deterministic for the smoke.
    os.environ["GSD_ARTIFACT_DELIVERY_MODE"] = str(args.delivery_mode)

    try:
        import fastmcp.settings

        docket_name = str(fastmcp.settings.docket.name or "fastmcp")
        docket_url = str(fastmcp.settings.docket.url)
    except Exception:  # noqa: BLE001
        docket_name = "fastmcp"
        docket_url = _env("FASTMCP_DOCKET_URL") or _env("DOCKET_URL") or ""

    if not docket_url:
        return {"ok": False, "error": "Missing docket url (fastmcp.settings.docket.url)."}

    session_id = str(uuid.uuid4())
    artifact_id = str(uuid.uuid4())
    now = time.time()

    png_bytes = base64.b64decode(_PNG_1X1_BASE64)
    shot = Screenshot(
        id=artifact_id,
        timestamp=now,
        screenshot_type="agent_step",
        source="smoke_artifacts",
        session_id=session_id,
        has_error=False,
        metadata={"note": "smoke_artifacts"},
        image_bytes=png_bytes,
        mime_type="image/png",
        url="https://example.com/smoke",
        step=1,
    )

    from fastmcp.server.dependencies import _current_docket

    docket = Docket(name=docket_name, url=docket_url)
    cleanup_attempted: bool | None = None
    async with docket:
        token = _current_docket.set(docket)
        try:
            identity = _build_identity(tenant_id=args.tenant_id, subject_id=args.subject_id)
            with identity_scope(identity):
                await persist_screenshot(shot, identity=identity)
                results = await get_screenshots(
                    last_n=1,
                    screenshot_type="agent_step",
                    session_id=session_id,
                    include_images=True,
                )

                if args.cleanup:
                    cleanup_attempted = True
                    try:
                        from .artifact_index import get_artifact_index_store
                        from .azure_blob_client import get_azure_blob_client

                        store = get_artifact_index_store()
                        record = await store.get_meta(artifact_id)
                        if record is not None:
                            try:
                                azure = get_azure_blob_client()
                                azure.delete(blob_name=str(record.s3_key))
                            except Exception:  # noqa: BLE001
                                pass
                            try:
                                await store.delete_meta(artifact_id)
                                await store.remove_from_session_zset(
                                    artifact_id=artifact_id,
                                    tenant_id=str(record.tenant_id),
                                    subject_id=str(record.subject_id),
                                    session_id=str(record.session_id),
                                    kind=record.artifact_kind,
                                )
                            except Exception:  # noqa: BLE001
                                pass
                    except Exception:  # noqa: BLE001
                        cleanup_attempted = False
        finally:
            _current_docket.reset(token)

    payload = None
    images: list[str] = []
    for item in results:
        if getattr(item, "type", None) == "text" and payload is None:
            try:
                payload = json.loads(str(getattr(item, "text", "") or "{}"))
            except Exception:  # noqa: BLE001
                payload = None
        elif getattr(item, "type", None) == "image":
            images.append(str(getattr(item, "data", "") or ""))

    screenshots = []
    if isinstance(payload, dict):
        screenshots = payload.get("screenshots") or []

    inline_ok = any(_validate_png_base64(img) for img in images if img)
    presigned_url_ok = False
    first_meta: dict[str, Any] | None = None
    if isinstance(screenshots, list) and screenshots and isinstance(screenshots[0], dict):
        first_meta = screenshots[0]
        artifact_meta = first_meta.get("artifact") if isinstance(first_meta, dict) else None
        if isinstance(artifact_meta, dict) and artifact_meta.get("url"):
            presigned_url_ok = True
    meta_inline_included = bool(
        screenshots
        and isinstance(screenshots, list)
        and isinstance(screenshots[0], dict)
        and bool(screenshots[0].get("inline_included"))
    )

    require_inline = str(args.delivery_mode) in {"inline", "both"}
    require_presigned = str(args.delivery_mode) in {"presigned", "both"}
    ok = bool(screenshots) and (inline_ok if require_inline else True) and (
        presigned_url_ok if require_presigned else True
    )

    report: dict[str, Any] = {
        "ok": ok,
        "delivery_mode": str(args.delivery_mode),
        "tenant_id": str(args.tenant_id),
        "subject_id": str(args.subject_id),
        "session_id": session_id,
        "artifact_id": artifact_id,
        "screenshots_count": len(screenshots) if isinstance(screenshots, list) else None,
        "inline_images_count": len(images),
        "inline_png_ok": inline_ok,
        "presigned_url_ok": presigned_url_ok if require_presigned else None,
        "meta_inline_included": meta_inline_included,
        "error": (payload.get("error") if isinstance(payload, dict) else None),
    }

    if cleanup_attempted is not None:
        report["cleanup_attempted"] = cleanup_attempted

    return report


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    report = asyncio.run(_run_smoke(args))
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if report.get("ok") else 1)


if __name__ == "__main__":
    main()
