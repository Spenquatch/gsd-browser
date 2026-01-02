"""ASGI server for streaming frames and exposing /healthz."""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import Settings
from ..screenshot_manager import ScreenshotManager
from .cdp_screencast import CdpScreencastStreamer
from .env import normalize_streaming_mode, normalize_streaming_quality
from .security import (
    FixedWindowRateLimiter,
    NonceStore,
    authorize_socket_connection,
    get_security_logger,
    load_streaming_auth_config,
)
from .stats import StreamingStats

logger = logging.getLogger("gsd_browser.streaming")

DEFAULT_STREAM_NAMESPACE = "/stream"
DEFAULT_CTRL_NAMESPACE = "/ctrl"


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
            screenshot_type="stream_sample",
            image_bytes=image_bytes,
            mime_type=mime_type,
            session_id=session_id,
            captured_at=ts,
            metadata={"streaming_mode": "screenshot", **dict(metadata or {})},
        )


@dataclass
class ControlState:
    holder_sid: str | None = None
    held_since_ts: float | None = None
    paused: bool = False

    def snapshot(self) -> dict[str, Any]:
        return {
            "holder_sid": self.holder_sid,
            "held_since_ts": self.held_since_ts,
            "paused": self.paused,
        }


def create_streaming_app(
    *,
    settings: Settings,
    screenshots: ScreenshotManager | None = None,
) -> StreamingRuntime:
    streaming_mode = normalize_streaming_mode(settings.streaming_mode)
    streaming_quality = normalize_streaming_quality(settings.streaming_quality)

    frame_queue_max = 2
    stats = StreamingStats(streaming_mode=streaming_mode, frame_queue_max=frame_queue_max)
    screenshot_manager = screenshots or ScreenshotManager()

    auth_config = load_streaming_auth_config()
    cors_allowed_origins: list[str] | str = auth_config.allowed_origins or "*"
    sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=cors_allowed_origins)
    nonce_store = NonceStore(ttl_seconds=auth_config.nonce_ttl_seconds, uses=auth_config.nonce_uses)
    connect_limiter = FixedWindowRateLimiter(
        window_seconds=60, max_events=auth_config.per_sid_connects_per_minute
    )
    event_limiter = FixedWindowRateLimiter(
        window_seconds=60, max_events=auth_config.per_sid_events_per_minute
    )
    control_state = ControlState()
    cdp_streamer = CdpScreencastStreamer(
        sio=sio,
        stats=stats,
        screenshot_manager=screenshot_manager,
        quality=streaming_quality,
        namespace=DEFAULT_STREAM_NAMESPACE,
        frame_queue_max=frame_queue_max,
        sample_every_n=10
        if streaming_quality == "med"
        else (15 if streaming_quality == "low" else 5),
    )

    api_app = FastAPI()

    static_dir = Path(__file__).resolve().parent / "dashboard_static"
    api_app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @api_app.get("/")
    async def dashboard() -> HTMLResponse:
        index_path = static_dir / "index.html"
        return HTMLResponse(index_path.read_text(encoding="utf-8"))

    @api_app.get("/auth/config")
    async def auth_config_public() -> JSONResponse:
        return JSONResponse(auth_config.to_public_dict())

    @api_app.get("/auth/nonce")
    async def issue_nonce() -> JSONResponse:
        return JSONResponse(nonce_store.issue())

    @api_app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse(stats.snapshot())

    @sio.event(namespace=DEFAULT_STREAM_NAMESPACE)
    async def connect(sid: str, environ: dict[str, Any], auth: dict[str, Any] | None) -> None:
        if not authorize_socket_connection(
            config=auth_config,
            nonce_store=nonce_store,
            namespace=DEFAULT_STREAM_NAMESPACE,
            sid=sid,
            environ=environ,
            auth=auth,
            connect_limiter=connect_limiter,
        ):
            raise ConnectionRefusedError("unauthorized")
        logger.info("Client connected", extra={"sid": sid, "namespace": DEFAULT_STREAM_NAMESPACE})

    @sio.event(namespace=DEFAULT_STREAM_NAMESPACE)
    async def disconnect(sid: str) -> None:
        logger.info(
            "Client disconnected",
            extra={"sid": sid, "namespace": DEFAULT_STREAM_NAMESPACE},
        )

    async def _emit_control_state(*, to_sid: str | None = None) -> None:
        payload = control_state.snapshot()
        if to_sid is None:
            await sio.emit("control_state", payload, namespace=DEFAULT_CTRL_NAMESPACE)
        else:
            await sio.emit("control_state", payload, namespace=DEFAULT_CTRL_NAMESPACE, to=to_sid)

    def _allow_ctrl_event(*, sid: str, event: str) -> bool:
        allowed = event_limiter.allow(f"{DEFAULT_CTRL_NAMESPACE}:{sid}")
        if not allowed:
            get_security_logger().info(
                "rate_limited_event",
                extra={"namespace": DEFAULT_CTRL_NAMESPACE, "sid": sid, "event": event},
            )
        return allowed

    @sio.event(namespace=DEFAULT_CTRL_NAMESPACE)
    async def connect_ctrl(sid: str, environ: dict[str, Any], auth: dict[str, Any] | None) -> None:
        if not authorize_socket_connection(
            config=auth_config,
            nonce_store=nonce_store,
            namespace=DEFAULT_CTRL_NAMESPACE,
            sid=sid,
            environ=environ,
            auth=auth,
            connect_limiter=connect_limiter,
        ):
            raise ConnectionRefusedError("unauthorized")
        logger.info("Client connected", extra={"sid": sid, "namespace": DEFAULT_CTRL_NAMESPACE})
        await _emit_control_state(to_sid=sid)

    @sio.event(namespace=DEFAULT_CTRL_NAMESPACE)
    async def disconnect_ctrl(sid: str) -> None:
        logger.info("Client disconnected", extra={"sid": sid, "namespace": DEFAULT_CTRL_NAMESPACE})
        if control_state.holder_sid == sid:
            control_state.holder_sid = None
            control_state.held_since_ts = None
            control_state.paused = False
            await _emit_control_state()

    @sio.on("take_control", namespace=DEFAULT_CTRL_NAMESPACE)
    async def take_control(sid: str, _: Any) -> None:
        if not _allow_ctrl_event(sid=sid, event="take_control"):
            return
        if control_state.holder_sid is None:
            control_state.holder_sid = sid
            control_state.held_since_ts = time.time()
            control_state.paused = False
        elif control_state.holder_sid != sid:
            get_security_logger().info(
                "ctrl_already_held",
                extra={
                    "namespace": DEFAULT_CTRL_NAMESPACE,
                    "sid": sid,
                    "event": "take_control",
                    "holder_sid": control_state.holder_sid,
                },
            )
        await _emit_control_state()

    @sio.on("release_control", namespace=DEFAULT_CTRL_NAMESPACE)
    async def release_control(sid: str, _: Any) -> None:
        if not _allow_ctrl_event(sid=sid, event="release_control"):
            return
        if control_state.holder_sid == sid:
            control_state.holder_sid = None
            control_state.held_since_ts = None
            control_state.paused = False
        else:
            get_security_logger().info(
                "ctrl_not_holder",
                extra={
                    "namespace": DEFAULT_CTRL_NAMESPACE,
                    "sid": sid,
                    "event": "release_control",
                    "holder_sid": control_state.holder_sid,
                },
            )
        await _emit_control_state()

    @sio.on("pause_agent", namespace=DEFAULT_CTRL_NAMESPACE)
    async def pause_agent(sid: str, _: Any) -> None:
        if not _allow_ctrl_event(sid=sid, event="pause_agent"):
            return
        if control_state.holder_sid == sid:
            control_state.paused = True
        else:
            get_security_logger().info(
                "ctrl_not_holder",
                extra={
                    "namespace": DEFAULT_CTRL_NAMESPACE,
                    "sid": sid,
                    "event": "pause_agent",
                    "holder_sid": control_state.holder_sid,
                },
            )
        await _emit_control_state()

    @sio.on("resume_agent", namespace=DEFAULT_CTRL_NAMESPACE)
    async def resume_agent(sid: str, _: Any) -> None:
        if not _allow_ctrl_event(sid=sid, event="resume_agent"):
            return
        if control_state.holder_sid == sid:
            control_state.paused = False
        else:
            get_security_logger().info(
                "ctrl_not_holder",
                extra={
                    "namespace": DEFAULT_CTRL_NAMESPACE,
                    "sid": sid,
                    "event": "resume_agent",
                    "holder_sid": control_state.holder_sid,
                },
            )
        await _emit_control_state()

    asgi_app = socketio.ASGIApp(sio, other_asgi_app=api_app)
    return StreamingRuntime(
        asgi_app=asgi_app,
        api_app=api_app,
        sio=sio,
        stats=stats,
        screenshots=screenshot_manager,
        cdp_streamer=cdp_streamer,
    )


def run_streaming_server(*, settings: Settings, host: str, port: int) -> None:
    runtime = create_streaming_app(settings=settings)
    uvicorn.run(runtime.asgi_app, host=host, port=port, log_level="info")
