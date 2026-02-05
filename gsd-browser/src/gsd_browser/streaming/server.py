"""ASGI server for streaming frames and exposing /healthz."""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

import socketio
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import Settings
from ..screenshot_manager import ScreenshotManager
from .cdp_screencast import CdpScreencastStreamer
from .control_state import ControlState
from .env import normalize_streaming_mode, normalize_streaming_quality
from .security import (
    FixedWindowRateLimiter,
    NonceStore,
    authorize_socket_connection,
    get_security_logger,
    load_streaming_auth_config,
)
from .session_registry import SessionRegistry
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
    registry: SessionRegistry

    # sid → Identity mapping for JWT auth mode (ADR-0023)
    sid_identity_stream: dict[str, Any] = dataclass_field(default_factory=dict)
    sid_identity_ctrl: dict[str, Any] = dataclass_field(default_factory=dict)

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
        # Emit to session room if it exists, otherwise broadcast (backward compat)
        room = session_id if session_id else None
        await self.sio.emit(
            "browser_update", payload,
            namespace=DEFAULT_STREAM_NAMESPACE, room=room,
        )
        shot = self.screenshots.record_screenshot(
            screenshot_type="stream_sample",
            image_bytes=image_bytes,
            mime_type=mime_type,
            session_id=session_id,
            captured_at=ts,
            metadata={"streaming_mode": "screenshot", **dict(metadata or {})},
        )
        try:
            from ..optionb.screenshot_artifacts import persist_screenshot

            if shot is not None:
                await persist_screenshot(shot)
        except Exception:  # noqa: BLE001
            pass


def _api_auth_error(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail)


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
    jwt_verifier: Any | None = None
    if auth_config.auth_mode == "jwt":
        try:
            from ..optionb.identity import get_jwt_verifier

            jwt_verifier = get_jwt_verifier()
        except Exception:  # noqa: BLE001
            jwt_verifier = None

    cors_allowed_origins: list[str] | str = auth_config.allowed_origins or "*"
    sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=cors_allowed_origins)
    nonce_store = NonceStore(ttl_seconds=auth_config.nonce_ttl_seconds, uses=auth_config.nonce_uses)
    connect_limiter = FixedWindowRateLimiter(
        window_seconds=60, max_events=auth_config.per_sid_connects_per_minute
    )
    event_limiter = FixedWindowRateLimiter(
        window_seconds=60, max_events=auth_config.per_sid_events_per_minute
    )
    auto_pause_on_take_control = getattr(settings, "auto_pause_on_take_control", True)
    control_state = ControlState(auto_pause_on_take_control=bool(auto_pause_on_take_control))
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

    async def _require_dashboard_auth(request: Request) -> None:
        """Gate /dashboard behind JWT when auth_mode is jwt (ADR-0023).

        For smoke/debugging, allow passing the bearer token as either:
        - `Authorization: Bearer <token>` header (curl-friendly), or
        - `?token=<token>` query param (browser-friendly).
        """
        if auth_config.auth_mode != "jwt":
            return

        token = ""
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
        if not token:
            token = str(request.query_params.get("token") or "").strip()

        if not token:
            raise HTTPException(status_code=401, detail="Missing token")

        if jwt_verifier is None:
            raise HTTPException(status_code=503, detail="JWT verifier not configured")

        verifier = jwt_verifier
        access_token = await verifier.verify_token(token)
        if access_token is None:
            raise HTTPException(status_code=401, detail="Invalid token")

    @api_app.get("/")
    async def dashboard(request: Request) -> HTMLResponse:
        if auth_config.auth_mode == "jwt":
            await _require_dashboard_auth(request)
        index_path = static_dir / "index.html"
        return HTMLResponse(index_path.read_text(encoding="utf-8"))

    @api_app.get("/dashboard")
    async def dashboard_path(request: Request) -> HTMLResponse:
        await _require_dashboard_auth(request)
        index_path = static_dir / "index.html"
        return HTMLResponse(index_path.read_text(encoding="utf-8"))

    @api_app.get("/auth/config")
    async def auth_config_public() -> JSONResponse:
        return JSONResponse(auth_config.to_public_dict())

    @api_app.get("/auth/nonce")
    async def issue_nonce() -> JSONResponse:
        if auth_config.auth_mode == "jwt":
            raise HTTPException(status_code=404, detail="not_found")
        return JSONResponse(nonce_store.issue())

    @api_app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok", **stats.snapshot()})

    sid_identity_stream: dict[str, Any] = {}
    sid_identity_ctrl: dict[str, Any] = {}

    async def _verify_socket_jwt_identity(
        *,
        namespace: str,
        sid: str,
        environ: dict[str, Any],
        auth: dict[str, Any] | None,
        sid_identity_map: dict[str, Any],
    ) -> bool:
        if jwt_verifier is None:
            return False
        if not isinstance(auth, dict):
            return False
        token = auth.get("token")
        if not isinstance(token, str) or not token.strip():
            return False

        from ..optionb.identity import (
            GsdJwtVerifier,
            get_jwt_subject_id_claim_name,
            get_jwt_tenant_id_claim_name,
            identity_from_claims,
        )

        verifier = jwt_verifier
        access_token = None
        audience_mismatch: Any | None = None
        if isinstance(verifier, GsdJwtVerifier):
            access_token, audience_mismatch = await verifier.verify_token_with_audience_details(
                token
            )
        else:
            access_token = await verifier.verify_token(token)

        if access_token is None:
            extra: dict[str, Any] = {"sid": sid, "namespace": namespace}
            if audience_mismatch is not None:
                extra["expected_audience"] = getattr(audience_mismatch, "expected_audience", "")
                extra["actual_audience"] = getattr(audience_mismatch, "actual_audience", "")
            get_security_logger().info("socket_jwt_auth_failed", extra=extra)
            return False

        claims = getattr(access_token, "claims", {}) or {}
        try:
            identity = identity_from_claims(
                claims,
                tenant_id_claim=get_jwt_tenant_id_claim_name(),
                subject_id_claim=get_jwt_subject_id_claim_name(),
            )
        except ValueError:
            get_security_logger().info(
                "socket_jwt_invalid_claims",
                extra={"sid": sid, "namespace": namespace},
            )
            return False

        sid_identity_map[sid] = identity
        get_security_logger().info(
            "socket_jwt_verified",
            extra={
                "sid": sid,
                "namespace": namespace,
                "tenant_id": identity.tenant_id,
                "subject_id": identity.subject_id,
            },
        )

        try:
            await sio.save_session(sid, {"identity": identity}, namespace=namespace)
        except Exception:  # noqa: BLE001
            pass

        _ = environ
        return True

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
            jwt_verifier=jwt_verifier,
            sid_identity_map=sid_identity_stream,
        ):
            raise ConnectionRefusedError("unauthorized")
        if auth_config.auth_mode == "jwt":
            ok = await _verify_socket_jwt_identity(
                namespace=DEFAULT_STREAM_NAMESPACE,
                sid=sid,
                environ=environ,
                auth=auth,
                sid_identity_map=sid_identity_stream,
            )
            if not ok:
                raise ConnectionRefusedError("unauthorized")
        logger.info("Client connected", extra={"sid": sid, "namespace": DEFAULT_STREAM_NAMESPACE})

    @sio.event(namespace=DEFAULT_STREAM_NAMESPACE)
    async def disconnect(sid: str) -> None:
        sid_identity_stream.pop(sid, None)
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

    def _reject_input_event(
        *, sid: str, event: str, log_message: str, reason: str, payload: Any
    ) -> dict[str, Any]:
        holder_sid = control_state.current_holder_sid()
        paused = control_state.is_paused()
        get_security_logger().info(
            log_message,
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

    def _extract_session_id(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        raw = payload.get("session_id")
        if not isinstance(raw, str):
            return None
        normalized = raw.strip()
        return normalized or None

    def _ctrl_session_authorized(
        *,
        sid: str,
        event: str,
        payload: Any,
        require_active_session: bool,
    ) -> tuple[bool, str]:
        if auth_config.auth_mode != "jwt":
            return True, ""

        identity = sid_identity_ctrl.get(sid)
        if identity is None:
            return False, "unauthenticated"

        snapshot = control_state.snapshot()
        active_session_id = snapshot.get("active_session_id")
        if not isinstance(active_session_id, str) or not active_session_id.strip():
            return (False, "no_active_session") if require_active_session else (True, "")

        payload_session_id = _extract_session_id(payload)
        if payload_session_id is not None and payload_session_id != active_session_id:
            get_security_logger().info(
                "ctrl_wrong_session",
                extra={
                    "namespace": DEFAULT_CTRL_NAMESPACE,
                    "sid": sid,
                    "event": event,
                    "payload_session_id": payload_session_id,
                    "active_session_id": active_session_id,
                },
            )
            return False, "wrong_session"

        session = registry.get_session(active_session_id)
        if session is None:
            return False, "session_not_found"

        id_tenant = getattr(identity, "tenant_id", None)
        if id_tenant and id_tenant != session.owner_tenant_id:
            get_security_logger().info(
                "ctrl_forbidden_tenant_mismatch",
                extra={
                    "namespace": DEFAULT_CTRL_NAMESPACE,
                    "sid": sid,
                    "event": event,
                    "identity_tenant": id_tenant,
                    "session_tenant": session.owner_tenant_id,
                    "session_id": active_session_id,
                },
            )
            return False, "forbidden"

        return True, ""

    def _validate_input_payload(
        *, event: str, payload: Any
    ) -> tuple[dict[str, Any] | None, str | None]:
        if not isinstance(payload, dict):
            return None, "invalid_payload"

        def _maybe_add_modifiers(out: dict[str, Any]) -> None:
            for key in ("altKey", "ctrlKey", "metaKey", "shiftKey"):
                value = payload.get(key)
                if isinstance(value, bool):
                    out[key] = value

        if event in {"input_click", "input_move", "input_wheel"}:
            x = _normalize_float(payload.get("x"))
            y = _normalize_float(payload.get("y"))
            if x is None or y is None:
                return None, "invalid_coordinates"
            out: dict[str, Any] = {"x": x, "y": y}
            _maybe_add_modifiers(out)

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
            _maybe_add_modifiers(out)
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
        authorized, reason = _ctrl_session_authorized(
            sid=sid,
            event=event,
            payload=payload,
            require_active_session=True,
        )
        if not authorized:
            return _reject_input_event(
                sid=sid,
                event=event,
                log_message="ctrl_forbidden",
                reason=reason,
                payload=payload,
            )
        if not control_state.is_holder(sid=sid):
            return _reject_input_event(
                sid=sid,
                event=event,
                log_message="ctrl_not_holder",
                reason="not_holder",
                payload=payload,
            )
        if not control_state.is_paused():
            return _reject_input_event(
                sid=sid,
                event=event,
                log_message="ctrl_not_paused",
                reason="not_paused",
                payload=payload,
            )

        validated, error = _validate_input_payload(event=event, payload=payload)
        if error is not None:
            return _reject_input_event(
                sid=sid,
                event=event,
                log_message="ctrl_invalid_payload",
                reason=error,
                payload=payload,
            )

        if not control_state.has_active_session():
            return _reject_input_event(
                sid=sid,
                event=event,
                log_message="ctrl_no_active_session",
                reason="no_active_session",
                payload=payload,
            )

        # Try direct CDP dispatch first (immediate, like web-agent)
        result = await control_state.dispatch_input_directly(event, validated or {})
        if result.get("ok"):
            logger.info("ctrl input dispatched directly: event=%s", event)
            return {"ok": True}

        logger.info(
            "ctrl direct dispatch failed (%s), falling back to queue: event=%s",
            result.get("error"),
            event,
        )
        # Fall back to queue-based dispatch (drained by pause_gate)
        queue_result = control_state.enqueue_input_event(
            sid=sid, event=event, payload=validated or {}
        )
        return {"ok": True, **queue_result}

    async def _connect_ctrl_impl(
        sid: str, environ: dict[str, Any], auth: dict[str, Any] | None
    ) -> None:
        if not authorize_socket_connection(
            config=auth_config,
            nonce_store=nonce_store,
            namespace=DEFAULT_CTRL_NAMESPACE,
            sid=sid,
            environ=environ,
            auth=auth,
            connect_limiter=connect_limiter,
            jwt_verifier=jwt_verifier,
            sid_identity_map=sid_identity_ctrl,
        ):
            raise ConnectionRefusedError("unauthorized")
        if auth_config.auth_mode == "jwt":
            ok = await _verify_socket_jwt_identity(
                namespace=DEFAULT_CTRL_NAMESPACE,
                sid=sid,
                environ=environ,
                auth=auth,
                sid_identity_map=sid_identity_ctrl,
            )
            if not ok:
                raise ConnectionRefusedError("unauthorized")
        logger.info("Client connected", extra={"sid": sid, "namespace": DEFAULT_CTRL_NAMESPACE})
        await _emit_control_state(to_sid=sid)

    @sio.on("connect", namespace=DEFAULT_CTRL_NAMESPACE)
    async def connect_ctrl_reserved(
        sid: str, environ: dict[str, Any], auth: dict[str, Any] | None
    ) -> None:
        await _connect_ctrl_impl(sid, environ, auth)

    # Alias event used by unit tests (kept stable for direct handler invocation).
    @sio.on("connect_ctrl", namespace=DEFAULT_CTRL_NAMESPACE)
    async def connect_ctrl(sid: str, environ: dict[str, Any], auth: dict[str, Any] | None) -> None:
        await _connect_ctrl_impl(sid, environ, auth)

    async def _disconnect_ctrl_impl(sid: str) -> None:
        sid_identity_ctrl.pop(sid, None)
        logger.info("Client disconnected", extra={"sid": sid, "namespace": DEFAULT_CTRL_NAMESPACE})
        if control_state.is_holder(sid=sid):
            control_state.clear()
            await _emit_control_state()

    @sio.on("disconnect", namespace=DEFAULT_CTRL_NAMESPACE)
    async def disconnect_ctrl_reserved(sid: str) -> None:
        await _disconnect_ctrl_impl(sid)

    # Alias event used by unit tests (kept stable for direct handler invocation).
    @sio.on("disconnect_ctrl", namespace=DEFAULT_CTRL_NAMESPACE)
    async def disconnect_ctrl(sid: str) -> None:
        await _disconnect_ctrl_impl(sid)

    @sio.on("take_control", namespace=DEFAULT_CTRL_NAMESPACE)
    async def take_control(sid: str, payload: Any) -> dict[str, Any]:
        if not _allow_ctrl_event(sid=sid, event="take_control"):
            return {"ok": False, "error": "rate_limited"}
        authorized, reason = _ctrl_session_authorized(
            sid=sid,
            event="take_control",
            payload=payload,
            require_active_session=True,
        )
        if not authorized:
            get_security_logger().info(
                "ctrl_forbidden",
                extra={
                    "namespace": DEFAULT_CTRL_NAMESPACE,
                    "sid": sid,
                    "event": "take_control",
                    "reason": reason,
                },
            )
            return {"ok": False, "error": reason}
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
        return {"ok": True}

    @sio.on("release_control", namespace=DEFAULT_CTRL_NAMESPACE)
    async def release_control(sid: str, payload: Any) -> dict[str, Any]:
        if not _allow_ctrl_event(sid=sid, event="release_control"):
            return {"ok": False, "error": "rate_limited"}
        authorized, reason = _ctrl_session_authorized(
            sid=sid,
            event="release_control",
            payload=payload,
            require_active_session=False,
        )
        if not authorized:
            return {"ok": False, "error": reason}
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
        return {"ok": True}

    @sio.on("pause_agent", namespace=DEFAULT_CTRL_NAMESPACE)
    async def pause_agent(sid: str, payload: Any) -> dict[str, Any]:
        if not _allow_ctrl_event(sid=sid, event="pause_agent"):
            return {"ok": False, "error": "rate_limited"}
        authorized, reason = _ctrl_session_authorized(
            sid=sid,
            event="pause_agent",
            payload=payload,
            require_active_session=True,
        )
        if not authorized:
            return {"ok": False, "error": reason}
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
        return {"ok": True}

    @sio.on("resume_agent", namespace=DEFAULT_CTRL_NAMESPACE)
    async def resume_agent(sid: str, payload: Any) -> dict[str, Any]:
        if not _allow_ctrl_event(sid=sid, event="resume_agent"):
            return {"ok": False, "error": "rate_limited"}
        authorized, reason = _ctrl_session_authorized(
            sid=sid,
            event="resume_agent",
            payload=payload,
            require_active_session=True,
        )
        if not authorized:
            return {"ok": False, "error": reason}
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
        return {"ok": True}

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

    # Session registry for multi-session support (ADR-0026)
    registry = SessionRegistry(retention_seconds=3600.0)

    # Session room join handler (ADR-0024)
    @sio.on("join_session", namespace=DEFAULT_STREAM_NAMESPACE)
    async def join_session(sid: str, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            return {"ok": False, "error": "invalid_payload"}
        session_id = data.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            return {"ok": False, "error": "missing_session_id"}
        session_id = session_id.strip()

        # Check session exists in registry
        session = registry.get_session(session_id)
        if session is None:
            if auth_config.auth_mode == "jwt":
                # Fail closed in multi-tenant mode: unknown session cannot be authorized.
                get_security_logger().info(
                    "join_session_denied_unknown_session",
                    extra={"sid": sid, "session_id": session_id},
                )
                return {"ok": False, "error": "session_not_found"}

            # Backward compat for localhost dev: allow joining any room when registry is empty.
            logger.debug("join_session: session %s not in registry, allowing", session_id)
        elif auth_config.auth_mode == "jwt":
            identity = sid_identity_stream.get(sid)
            if identity is None:
                return {"ok": False, "error": "unauthenticated"}

            id_tenant = getattr(identity, "tenant_id", None)
            if id_tenant and id_tenant != session.owner_tenant_id:
                get_security_logger().info(
                    "join_session_denied_tenant_mismatch",
                    extra={
                        "sid": sid,
                        "session_id": session_id,
                        "identity_tenant": id_tenant,
                        "session_tenant": session.owner_tenant_id,
                    },
                )
                return {"ok": False, "error": "forbidden"}

        await sio.enter_room(sid, session_id, namespace=DEFAULT_STREAM_NAMESPACE)
        logger.info(
            "Client joined session room",
            extra={"sid": sid, "session_id": session_id},
        )
        return {"ok": True, "session_id": session_id}

    @sio.on("leave_session", namespace=DEFAULT_STREAM_NAMESPACE)
    async def leave_session(sid: str, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            return {"ok": False, "error": "invalid_payload"}
        session_id = data.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            return {"ok": False, "error": "missing_session_id"}
        session_id = session_id.strip()
        await sio.leave_room(sid, session_id, namespace=DEFAULT_STREAM_NAMESPACE)
        return {"ok": True}

    # JWT middleware for /api/v1/ endpoints (DA-7 / ADR-0023)
    async def _require_api_auth(request: Request) -> dict[str, Any] | None:
        """FastAPI dependency that validates JWT when auth_mode is jwt.

        Returns the verified identity dict, or None when auth is not
        required (hmac mode / local dev).
        """
        if not auth_config.auth_required or auth_config.auth_mode != "jwt":
            return None

        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            raise _api_auth_error("Missing Bearer token")

        token = auth_header[7:].strip()
        if not token:
            raise _api_auth_error("Empty Bearer token")

        if jwt_verifier is None:
            raise _api_auth_error("JWT verifier not configured")

        from ..optionb.identity import (
            GsdJwtVerifier,
            get_jwt_subject_id_claim_name,
            get_jwt_tenant_id_claim_name,
            identity_from_claims,
        )

        try:
            verifier = jwt_verifier
            access_token = None
            if isinstance(verifier, GsdJwtVerifier):
                access_token, _aud = await verifier.verify_token_with_audience_details(token)
            else:
                access_token = await verifier.verify_token(token)
            if access_token is None:
                raise _api_auth_error("Invalid token")
            claims = getattr(access_token, "claims", {}) or {}
            identity = identity_from_claims(
                claims,
                tenant_id_claim=get_jwt_tenant_id_claim_name(),
                subject_id_claim=get_jwt_subject_id_claim_name(),
            )
            return {"tenant_id": identity.tenant_id, "subject_id": identity.subject_id}
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            get_security_logger().info("api_jwt_auth_failed", extra={"error": str(exc)[:200]})
            raise _api_auth_error("Invalid token") from exc

    # Session management API endpoints (ADR-0026)
    @api_app.get("/api/v1/sessions")
    async def list_sessions(
        identity: dict[str, Any] | None = Depends(_require_api_auth),  # noqa: B008
    ) -> JSONResponse:
        all_sessions = registry.all_sessions()
        # Filter by tenant when JWT auth is active
        if identity is not None:
            tid = identity.get("tenant_id")
            all_sessions = [
                s for s in all_sessions
                if s.owner_tenant_id == tid
            ]
        return JSONResponse([
            {
                "session_id": s.session_id,
                "status": s.status.value,
                "tenant_id": s.owner_tenant_id,
                "subject_id": s.owner_subject_id,
                "worker_id": s.worker_id,
                "stream_url": s.stream_url,
                "created_at": s.created_at,
                "last_activity_at": s.last_activity_at,
            }
            for s in all_sessions
        ])

    @api_app.get("/api/v1/sessions/{session_id}")
    async def get_session_detail(
        session_id: str,
        identity: dict[str, Any] | None = Depends(_require_api_auth),  # noqa: B008
    ) -> JSONResponse:
        session = registry.get_session(session_id)
        if session is None:
            return JSONResponse(
                {"error": "Session not found"}, status_code=404
            )
        # Tenant-scoped access check
        if identity is not None:
            tid = identity.get("tenant_id")
            if tid and session.owner_tenant_id != tid:
                return JSONResponse(
                    {"error": "Forbidden"}, status_code=403
                )
        return JSONResponse({
            "session_id": session.session_id,
            "status": session.status.value,
            "tenant_id": session.owner_tenant_id,
            "subject_id": session.owner_subject_id,
            "worker_id": session.worker_id,
            "stream_url": session.stream_url,
            "created_at": session.created_at,
            "last_activity_at": session.last_activity_at,
        })

    @api_app.post("/api/v1/sessions/{session_id}/terminate")
    async def terminate_session_endpoint(
        session_id: str,
        identity: dict[str, Any] | None = Depends(_require_api_auth),  # noqa: B008
    ) -> JSONResponse:
        session = registry.get_session(session_id)
        if session is None:
            return JSONResponse(
                {"error": "Session not found"}, status_code=404
            )
        if identity is not None:
            tid = identity.get("tenant_id")
            if tid and session.owner_tenant_id != tid:
                return JSONResponse(
                    {"error": "Forbidden"}, status_code=403
                )
        try:
            registry.terminate_session(session_id)
        except ValueError as exc:
            return JSONResponse(
                {"error": str(exc)}, status_code=409
            )
        return JSONResponse({"ok": True, "session_id": session_id})

    # Session-affinity health check (RS-5 / ADR-0024)
    worker_id = getattr(settings, "worker_id", "") or ""

    @api_app.get("/healthz/worker")
    async def worker_healthz() -> JSONResponse:
        all_active = sum(
            1 for s in registry.all_sessions() if s.is_active()
        )
        return JSONResponse({
            "worker_id": worker_id,
            "active_sessions": all_active,
            **stats.snapshot(),
        })

    @api_app.get("/healthz/sessions/{session_id}")
    async def session_healthz(session_id: str) -> JSONResponse:
        sid = (session_id or "").strip()
        if not sid:
            raise HTTPException(status_code=404, detail="not_found")
        session = registry.get_session(sid)
        if session is None or not session.is_active():
            raise HTTPException(status_code=404, detail="not_found")
        return JSONResponse(
            {
                "ok": True,
                "session_id": session.session_id,
                "worker_id": worker_id,
                "status": session.status.value,
            }
        )

    asgi_app = socketio.ASGIApp(sio, other_asgi_app=api_app)
    return StreamingRuntime(
        asgi_app=asgi_app,
        api_app=api_app,
        sio=sio,
        stats=stats,
        screenshots=screenshot_manager,
        cdp_streamer=cdp_streamer,
        control_state=control_state,
        registry=registry,
        sid_identity_stream=sid_identity_stream,
        sid_identity_ctrl=sid_identity_ctrl,
    )


def run_streaming_server(*, settings: Settings, host: str, port: int) -> None:
    runtime = create_streaming_app(settings=settings)
    uvicorn.run(runtime.asgi_app, host=host, port=port, log_level="info")
