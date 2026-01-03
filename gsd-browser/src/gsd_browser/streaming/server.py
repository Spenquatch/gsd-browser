"""ASGI server for streaming frames and exposing /healthz."""

from __future__ import annotations

import asyncio
import base64
import logging
import threading
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
    control_state: ControlState

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


class ControlState:
    """Thread-safe control state shared across the dashboard thread and tool runtime."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._unpaused = threading.Event()
        self._unpaused.set()

        self.holder_sid: str | None = None
        self.held_since_ts: float | None = None
        self.paused: bool = False
        self._input_events: list[dict[str, Any]] = []
        self._input_events_max = 1000
        self._input_seq = 0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "holder_sid": self.holder_sid,
                "held_since_ts": self.held_since_ts,
                "paused": self.paused,
            }

    def enqueue_input_event(
        self, *, sid: str, event: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        with self._lock:
            self._input_seq += 1
            record = {
                "seq": self._input_seq,
                "received_at": time.time(),
                "sid": sid,
                "event": event,
                "payload": payload,
            }
            self._input_events.append(record)
            dropped: dict[str, Any] | None = None
            if len(self._input_events) > self._input_events_max:
                dropped = self._input_events.pop(0)
            if dropped is not None:
                get_security_logger().info(
                    "ctrl_input_dropped",
                    extra={
                        "namespace": DEFAULT_CTRL_NAMESPACE,
                        "sid": sid,
                        "event": event,
                        "dropped_seq": dropped.get("seq"),
                        "dropped_event": dropped.get("event"),
                        "queued": len(self._input_events),
                        "reason": "buffer_full",
                    },
                )
            return {"queued": len(self._input_events), "dropped": dropped is not None}

    def drain_input_events(self, *, max_items: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if max_items is None or max_items <= 0:
                drained = list(self._input_events)
                self._input_events.clear()
                return drained
            drained = self._input_events[:max_items]
            del self._input_events[:max_items]
            return drained

    def current_holder_sid(self) -> str | None:
        with self._lock:
            return self.holder_sid

    def is_holder(self, *, sid: str) -> bool:
        with self._lock:
            return self.holder_sid == sid

    def is_paused(self) -> bool:
        with self._lock:
            return self.paused

    def _set_paused_locked(self, paused: bool) -> None:
        self.paused = paused
        if paused:
            self._unpaused.clear()
        else:
            self._unpaused.set()

    def clear(self) -> None:
        with self._lock:
            self.holder_sid = None
            self.held_since_ts = None
            self._set_paused_locked(False)
            self._input_events.clear()

    def take_control(self, *, sid: str) -> None:
        with self._lock:
            if self.holder_sid is None:
                self.holder_sid = sid
                self.held_since_ts = time.time()
                self._set_paused_locked(False)

    def release_control(self, *, sid: str) -> None:
        with self._lock:
            if self.holder_sid == sid:
                self.holder_sid = None
                self.held_since_ts = None
                self._set_paused_locked(False)

    def pause_if_holder(self, *, sid: str) -> bool:
        with self._lock:
            if self.holder_sid != sid:
                return False
            self._set_paused_locked(True)
            return True

    def resume_if_holder(self, *, sid: str) -> bool:
        with self._lock:
            if self.holder_sid != sid:
                return False
            self._set_paused_locked(False)
            return True

    async def wait_until_unpaused(self) -> None:
        if not self.is_paused():
            return
        await asyncio.to_thread(self._unpaused.wait)


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

    def _normalize_float(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None

    def _normalize_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return None
        return None

    def _normalize_str(value: Any) -> str | None:
        if isinstance(value, str):
            return value
        return None

    def _redacted_payload_meta(*, event: str, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {"payload_type": type(payload).__name__}
        meta: dict[str, Any] = {"payload_keys": sorted(payload.keys())}
        if event == "input_type":
            text = payload.get("text")
            if isinstance(text, str):
                meta["text_len"] = len(text)
        return meta

    def _reject_input_event(*, sid: str, event: str, reason: str, payload: Any) -> dict[str, Any]:
        holder_sid = control_state.current_holder_sid()
        paused = control_state.is_paused()
        get_security_logger().info(
            "ctrl_input_rejected",
            extra={
                "namespace": DEFAULT_CTRL_NAMESPACE,
                "sid": sid,
                "event": event,
                "reason": reason,
                "holder_sid": holder_sid,
                "paused": paused,
                **_redacted_payload_meta(event=event, payload=payload),
            },
        )
        return {"ok": False, "error": reason}

    def _validate_input_payload(
        *, event: str, payload: Any
    ) -> tuple[dict[str, Any] | None, str | None]:
        if not isinstance(payload, dict):
            return None, "invalid_payload"

        if event in {"input_click", "input_move", "input_wheel"}:
            x = _normalize_float(payload.get("x"))
            y = _normalize_float(payload.get("y"))
            if x is None or y is None:
                return None, "invalid_coordinates"
            out: dict[str, Any] = {"x": x, "y": y}

            if event == "input_wheel":
                dx = _normalize_float(payload.get("delta_x"))
                dy = _normalize_float(payload.get("delta_y"))
                if dx is None or dy is None:
                    return None, "invalid_wheel_delta"
                out["delta_x"] = dx
                out["delta_y"] = dy

            if event == "input_click":
                button = _normalize_str(payload.get("button")) or "left"
                if button not in {"left", "middle", "right"}:
                    return None, "invalid_button"
                out["button"] = button
                click_count = _normalize_int(payload.get("click_count"))
                if click_count is not None:
                    if click_count < 1 or click_count > 10:
                        return None, "invalid_click_count"
                    out["click_count"] = click_count

            return out, None

        if event in {"input_keydown", "input_keyup"}:
            key = _normalize_str(payload.get("key"))
            if not key:
                return None, "invalid_key"
            out = {"key": key}
            code = _normalize_str(payload.get("code"))
            if code:
                out["code"] = code
            repeat = payload.get("repeat")
            if isinstance(repeat, bool):
                out["repeat"] = repeat
            return out, None

        if event == "input_type":
            text = _normalize_str(payload.get("text"))
            if text is None:
                return None, "invalid_text"
            if len(text) > 2000:
                return None, "text_too_long"
            return {"text": text}, None

        return None, "unknown_event"

    async def _handle_ctrl_input_event(*, sid: str, event: str, payload: Any) -> dict[str, Any]:
        if not _allow_ctrl_event(sid=sid, event=event):
            return {"ok": False, "error": "rate_limited"}
        if not control_state.is_holder(sid=sid):
            return _reject_input_event(sid=sid, event=event, reason="not_holder", payload=payload)
        if not control_state.is_paused():
            return _reject_input_event(sid=sid, event=event, reason="not_paused", payload=payload)

        validated, error = _validate_input_payload(event=event, payload=payload)
        if error is not None:
            return _reject_input_event(sid=sid, event=event, reason=error, payload=payload)

        queue_result = control_state.enqueue_input_event(
            sid=sid, event=event, payload=validated or {}
        )
        return {"ok": True, **queue_result}

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
        if control_state.is_holder(sid=sid):
            control_state.clear()
            await _emit_control_state()

    @sio.on("take_control", namespace=DEFAULT_CTRL_NAMESPACE)
    async def take_control(sid: str, _: Any) -> None:
        if not _allow_ctrl_event(sid=sid, event="take_control"):
            return
        holder_sid = control_state.current_holder_sid()
        if holder_sid is None:
            control_state.take_control(sid=sid)
        elif holder_sid != sid:
            get_security_logger().info(
                "ctrl_already_held",
                extra={
                    "namespace": DEFAULT_CTRL_NAMESPACE,
                    "sid": sid,
                    "event": "take_control",
                    "holder_sid": holder_sid,
                },
            )
        await _emit_control_state()

    @sio.on("release_control", namespace=DEFAULT_CTRL_NAMESPACE)
    async def release_control(sid: str, _: Any) -> None:
        if not _allow_ctrl_event(sid=sid, event="release_control"):
            return
        holder_sid = control_state.current_holder_sid()
        if holder_sid == sid:
            control_state.release_control(sid=sid)
        else:
            get_security_logger().info(
                "ctrl_not_holder",
                extra={
                    "namespace": DEFAULT_CTRL_NAMESPACE,
                    "sid": sid,
                    "event": "release_control",
                    "holder_sid": holder_sid,
                },
            )
        await _emit_control_state()

    @sio.on("pause_agent", namespace=DEFAULT_CTRL_NAMESPACE)
    async def pause_agent(sid: str, _: Any) -> None:
        if not _allow_ctrl_event(sid=sid, event="pause_agent"):
            return
        if not control_state.pause_if_holder(sid=sid):
            holder_sid = control_state.current_holder_sid()
            get_security_logger().info(
                "ctrl_not_holder",
                extra={
                    "namespace": DEFAULT_CTRL_NAMESPACE,
                    "sid": sid,
                    "event": "pause_agent",
                    "holder_sid": holder_sid,
                },
            )
        await _emit_control_state()

    @sio.on("resume_agent", namespace=DEFAULT_CTRL_NAMESPACE)
    async def resume_agent(sid: str, _: Any) -> None:
        if not _allow_ctrl_event(sid=sid, event="resume_agent"):
            return
        if not control_state.resume_if_holder(sid=sid):
            holder_sid = control_state.current_holder_sid()
            get_security_logger().info(
                "ctrl_not_holder",
                extra={
                    "namespace": DEFAULT_CTRL_NAMESPACE,
                    "sid": sid,
                    "event": "resume_agent",
                    "holder_sid": holder_sid,
                },
            )
        await _emit_control_state()

    @sio.on("input_click", namespace=DEFAULT_CTRL_NAMESPACE)
    async def input_click(sid: str, payload: Any) -> dict[str, Any]:
        return await _handle_ctrl_input_event(sid=sid, event="input_click", payload=payload)

    @sio.on("input_move", namespace=DEFAULT_CTRL_NAMESPACE)
    async def input_move(sid: str, payload: Any) -> dict[str, Any]:
        return await _handle_ctrl_input_event(sid=sid, event="input_move", payload=payload)

    @sio.on("input_wheel", namespace=DEFAULT_CTRL_NAMESPACE)
    async def input_wheel(sid: str, payload: Any) -> dict[str, Any]:
        return await _handle_ctrl_input_event(sid=sid, event="input_wheel", payload=payload)

    @sio.on("input_keydown", namespace=DEFAULT_CTRL_NAMESPACE)
    async def input_keydown(sid: str, payload: Any) -> dict[str, Any]:
        return await _handle_ctrl_input_event(sid=sid, event="input_keydown", payload=payload)

    @sio.on("input_keyup", namespace=DEFAULT_CTRL_NAMESPACE)
    async def input_keyup(sid: str, payload: Any) -> dict[str, Any]:
        return await _handle_ctrl_input_event(sid=sid, event="input_keyup", payload=payload)

    @sio.on("input_type", namespace=DEFAULT_CTRL_NAMESPACE)
    async def input_type(sid: str, payload: Any) -> dict[str, Any]:
        return await _handle_ctrl_input_event(sid=sid, event="input_type", payload=payload)

    asgi_app = socketio.ASGIApp(sio, other_asgi_app=api_app)
    return StreamingRuntime(
        asgi_app=asgi_app,
        api_app=api_app,
        sio=sio,
        stats=stats,
        screenshots=screenshot_manager,
        cdp_streamer=cdp_streamer,
        control_state=control_state,
    )


def run_streaming_server(*, settings: Settings, host: str, port: int) -> None:
    runtime = create_streaming_app(settings=settings)
    uvicorn.run(runtime.asgi_app, host=host, port=port, log_level="info")
