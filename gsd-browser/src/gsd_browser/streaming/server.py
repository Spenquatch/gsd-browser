"""ASGI server for streaming frames and exposing /healthz."""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from typing import Any

import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ..config import Settings
from ..screenshot_manager import ScreenshotManager
from .cdp_screencast import CdpScreencastStreamer
from .env import normalize_streaming_mode, normalize_streaming_quality
from .stats import StreamingStats

logger = logging.getLogger("gsd_browser.streaming")

DEFAULT_STREAM_NAMESPACE = "/stream"


@dataclass(frozen=True)
class StreamingRuntime:
    asgi_app: Any
    api_app: FastAPI
    sio: socketio.AsyncServer
    stats: StreamingStats
    screenshots: ScreenshotManager
    cdp_streamer: CdpScreencastStreamer

    async def emit_browser_update(
        self,
        *,
        session_id: str,
        image_bytes: bytes,
        mime_type: str,
        timestamp: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        ts = timestamp if timestamp is not None else time.time()
        payload = {
            "session_id": session_id,
            "timestamp": ts,
            "mime_type": mime_type,
            "image_base64": base64.b64encode(image_bytes).decode("ascii"),
            "metadata": dict(metadata or {}),
        }
        await self.sio.emit("browser_update", payload, namespace=DEFAULT_STREAM_NAMESPACE)
        self.screenshots.record_screenshot(
            screenshot_type="browser_update",
            image_bytes=image_bytes,
            mime_type=mime_type,
            session_id=session_id,
            captured_at=ts,
            metadata={"streaming_mode": "screenshot", **dict(metadata or {})},
        )


def create_streaming_app(*, settings: Settings) -> StreamingRuntime:
    streaming_mode = normalize_streaming_mode(settings.streaming_mode)
    streaming_quality = normalize_streaming_quality(settings.streaming_quality)

    frame_queue_max = 2
    stats = StreamingStats(streaming_mode=streaming_mode, frame_queue_max=frame_queue_max)
    screenshots = ScreenshotManager()

    sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
    cdp_streamer = CdpScreencastStreamer(
        sio=sio,
        stats=stats,
        screenshot_manager=screenshots,
        quality=streaming_quality,
        namespace=DEFAULT_STREAM_NAMESPACE,
        frame_queue_max=frame_queue_max,
        sample_every_n=10
        if streaming_quality == "med"
        else (15 if streaming_quality == "low" else 5),
    )

    api_app = FastAPI()

    @api_app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse(stats.snapshot())

    @sio.event(namespace=DEFAULT_STREAM_NAMESPACE)
    async def connect(sid: str, environ: dict[str, Any]) -> None:  # noqa: ARG001
        logger.info("Client connected", extra={"sid": sid, "namespace": DEFAULT_STREAM_NAMESPACE})

    @sio.event(namespace=DEFAULT_STREAM_NAMESPACE)
    async def disconnect(sid: str) -> None:
        logger.info(
            "Client disconnected",
            extra={"sid": sid, "namespace": DEFAULT_STREAM_NAMESPACE},
        )

    asgi_app = socketio.ASGIApp(sio, other_asgi_app=api_app)
    return StreamingRuntime(
        asgi_app=asgi_app,
        api_app=api_app,
        sio=sio,
        stats=stats,
        screenshots=screenshots,
        cdp_streamer=cdp_streamer,
    )


def run_streaming_server(*, settings: Settings, host: str, port: int) -> None:
    runtime = create_streaming_app(settings=settings)
    uvicorn.run(runtime.asgi_app, host=host, port=port, log_level="info")
