"""Security helpers for the streaming server (auth, nonce, rate limiting, logging)."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any

from ..logging_utils import JsonFormatter

logger = logging.getLogger("gsd_browser.streaming")


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


def _parse_int(value: str | None, *, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value.strip())
    except ValueError:
        return default
    return parsed


def _parse_allowed_origins(value: str | None) -> list[str] | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized == "*":
        return None
    parts = [p.strip() for p in normalized.split(",") if p.strip()]
    return parts or None


@dataclass(frozen=True)
class StreamingAuthConfig:
    auth_required: bool
    api_key: str | None
    allowed_origins: list[str] | None
    nonce_ttl_seconds: int
    nonce_uses: int
    per_sid_events_per_minute: int
    per_sid_connects_per_minute: int

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "auth_required": self.auth_required,
            "nonce_ttl_seconds": self.nonce_ttl_seconds,
            "nonce_uses": self.nonce_uses,
            "per_sid_events_per_minute": self.per_sid_events_per_minute,
            "per_sid_connects_per_minute": self.per_sid_connects_per_minute,
        }


def load_streaming_auth_config() -> StreamingAuthConfig:
    auth_required = _parse_bool(os.environ.get("STREAMING_AUTH_REQUIRED"), default=False)
    api_key = os.environ.get("STREAMING_API_KEY") or None
    allowed_origins = _parse_allowed_origins(os.environ.get("STREAMING_ALLOWED_ORIGINS"))

    nonce_ttl_seconds = _parse_int(os.environ.get("STREAMING_NONCE_TTL_SECONDS"), default=60)
    nonce_uses = _parse_int(os.environ.get("STREAMING_NONCE_USES"), default=4)
    per_sid_events_per_minute = _parse_int(
        os.environ.get("STREAMING_RATE_LIMIT_EVENTS_PER_MINUTE"), default=120
    )
    per_sid_connects_per_minute = _parse_int(
        os.environ.get("STREAMING_RATE_LIMIT_CONNECTS_PER_MINUTE"), default=30
    )

    if auth_required and not api_key:
        raise RuntimeError("STREAMING_AUTH_REQUIRED is set but STREAMING_API_KEY is empty")

    return StreamingAuthConfig(
        auth_required=auth_required,
        api_key=api_key,
        allowed_origins=allowed_origins,
        nonce_ttl_seconds=max(5, nonce_ttl_seconds),
        nonce_uses=max(1, nonce_uses),
        per_sid_events_per_minute=max(1, per_sid_events_per_minute),
        per_sid_connects_per_minute=max(1, per_sid_connects_per_minute),
    )


def get_security_logger() -> logging.Logger:
    sec = logging.getLogger("gsd_browser.security")
    sec.setLevel(logging.INFO)
    if any(
        isinstance(handler, logging.FileHandler) and handler.baseFilename.endswith("security.log")
        for handler in sec.handlers
    ):
        return sec

    handler = logging.FileHandler("security.log", encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    sec.addHandler(handler)
    sec.propagate = False
    return sec


def _get_header(environ: dict[str, Any], header_name: str) -> str | None:
    key = "HTTP_" + header_name.upper().replace("-", "_")
    raw = environ.get(key)
    if isinstance(raw, str) and raw:
        return raw

    scope = environ.get("asgi.scope")
    if isinstance(scope, dict):
        headers = scope.get("headers")
        if isinstance(headers, list):
            needle = header_name.lower().encode("ascii")
            for k, v in headers:
                if k == needle:
                    try:
                        return v.decode("utf-8")
                    except Exception:  # noqa: BLE001
                        return None
    return None


def get_origin(environ: dict[str, Any]) -> str | None:
    return _get_header(environ, "origin")


def get_client_ip(environ: dict[str, Any]) -> str | None:
    scope = environ.get("asgi.scope")
    if isinstance(scope, dict):
        client = scope.get("client")
        if isinstance(client, (list, tuple)) and client and isinstance(client[0], str):
            return client[0]
    for key in ("REMOTE_ADDR", "HTTP_X_FORWARDED_FOR"):
        raw = environ.get(key)
        if isinstance(raw, str) and raw:
            return raw.split(",")[0].strip()
    return None


class NonceStore:
    def __init__(self, *, ttl_seconds: int, uses: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._uses = uses
        self._nonces: dict[str, tuple[float, int]] = {}

    def issue(self) -> dict[str, Any]:
        now = time.time()
        nonce = secrets.token_urlsafe(24)
        expires_at = now + float(self._ttl_seconds)
        self._nonces[nonce] = (expires_at, self._uses)
        self._gc(now)
        return {"nonce": nonce, "expires_at": expires_at}

    def validate(self, *, nonce: str, sig_hex: str, api_key: str) -> bool:
        now = time.time()
        record = self._nonces.get(nonce)
        if not record:
            return False
        expires_at, uses_left = record
        if expires_at < now or uses_left <= 0:
            self._nonces.pop(nonce, None)
            return False
        expected = hmac.new(
            api_key.encode("utf-8"), nonce.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, sig_hex):
            return False
        uses_left -= 1
        if uses_left <= 0:
            self._nonces.pop(nonce, None)
        else:
            self._nonces[nonce] = (expires_at, uses_left)
        self._gc(now)
        return True

    def _gc(self, now: float) -> None:
        expired = [nonce for nonce, (expires_at, _) in self._nonces.items() if expires_at < now]
        for nonce in expired:
            self._nonces.pop(nonce, None)


class FixedWindowRateLimiter:
    def __init__(self, *, window_seconds: int, max_events: int) -> None:
        self._window_seconds = float(window_seconds)
        self._max_events = max_events
        self._state: dict[str, tuple[float, int]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        window_start, count = self._state.get(key, (now, 0))
        if now - window_start >= self._window_seconds:
            window_start, count = now, 0
        count += 1
        self._state[key] = (window_start, count)
        return count <= self._max_events


def authorize_socket_connection(
    *,
    config: StreamingAuthConfig,
    nonce_store: NonceStore,
    namespace: str,
    sid: str,
    environ: dict[str, Any],
    auth: dict[str, Any] | None,
    connect_limiter: FixedWindowRateLimiter,
) -> bool:
    sec = get_security_logger()

    if not connect_limiter.allow(f"{namespace}:{sid}:connect"):
        sec.info(
            "rate_limited_connect",
            extra={
                "namespace": namespace,
                "sid": sid,
                "ip": get_client_ip(environ),
                "origin": get_origin(environ),
            },
        )
        return False

    if not config.auth_required:
        return True

    origin = get_origin(environ)
    if config.allowed_origins is not None and origin not in config.allowed_origins:
        sec.info(
            "origin_rejected",
            extra={
                "namespace": namespace,
                "sid": sid,
                "ip": get_client_ip(environ),
                "origin": origin,
            },
        )
        return False

    if not config.api_key:
        logger.error("Auth required but STREAMING_API_KEY is missing")
        return False

    if not isinstance(auth, dict):
        sec.info(
            "missing_auth",
            extra={
                "namespace": namespace,
                "sid": sid,
                "ip": get_client_ip(environ),
                "origin": origin,
            },
        )
        return False

    nonce = auth.get("nonce")
    sig = auth.get("sig")
    if not isinstance(nonce, str) or not isinstance(sig, str):
        sec.info(
            "missing_nonce_sig",
            extra={
                "namespace": namespace,
                "sid": sid,
                "ip": get_client_ip(environ),
                "origin": origin,
            },
        )
        return False

    if not nonce_store.validate(nonce=nonce, sig_hex=sig, api_key=config.api_key):
        sec.info(
            "bad_nonce_sig",
            extra={
                "namespace": namespace,
                "sid": sid,
                "ip": get_client_ip(environ),
                "origin": origin,
            },
        )
        return False

    return True
