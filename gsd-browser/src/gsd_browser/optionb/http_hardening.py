from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from starlette.responses import JSONResponse


def _env(name: str) -> str:
    return str(os.environ.get(name, "")).strip()


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "t", "yes", "y", "on"}


def _http_headers(scope: Mapping[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in scope.get("headers") or []:
        try:
            headers[key.decode("latin-1").lower()] = value.decode("latin-1")
        except Exception:  # noqa: BLE001
            continue
    return headers


DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://localhost",
    "http://127.0.0.1",
    "http://[::1]",
)


@dataclass(frozen=True, slots=True)
class OriginPattern:
    scheme: str
    hostname: str
    port: int | None  # None means "any port"


@dataclass(frozen=True, slots=True)
class LocalHttpHardeningConfig:
    allowed_origins: tuple[OriginPattern, ...]
    allow_null_origin: bool
    allowed_hosts: frozenset[str]


def _parse_allowed_origins_from_env() -> list[str]:
    raw = _env("GSD_HTTP_ALLOWED_ORIGINS")
    if not raw:
        return list(DEFAULT_ALLOWED_ORIGINS)
    parts = [part.strip() for part in raw.split(",")]
    return [part for part in parts if part]


def _origin_pattern(value: str) -> OriginPattern:
    parsed = urlsplit(value)
    scheme = (parsed.scheme or "").lower()
    if not scheme or not parsed.hostname:
        raise ValueError(f"Invalid origin (expected scheme://host[:port]): {value}")
    return OriginPattern(
        scheme=scheme,
        hostname=parsed.hostname.lower(),
        port=parsed.port,
    )


def load_local_http_hardening_config_from_env() -> LocalHttpHardeningConfig:
    """Load local HTTP hardening config pinned by ADR-0014.

    - Allowed origins are controlled by `GSD_HTTP_ALLOWED_ORIGINS` (comma-separated).
    - Null origin is controlled by `GSD_HTTP_ALLOW_NULL_ORIGIN` (default false).
    - Host allowlist is derived from the allowed origins + localhost defaults.
    """

    allowed_origins_raw = _parse_allowed_origins_from_env()
    allowed_origin_patterns = tuple(_origin_pattern(value) for value in allowed_origins_raw)

    allowed_hosts = {pattern.hostname for pattern in allowed_origin_patterns}
    allowed_hosts.update({"localhost", "127.0.0.1", "::1"})

    return LocalHttpHardeningConfig(
        allowed_origins=allowed_origin_patterns,
        allow_null_origin=_env_bool("GSD_HTTP_ALLOW_NULL_ORIGIN", default=False),
        allowed_hosts=frozenset(allowed_hosts),
    )


def _is_allowed_origin(*, origin: str, config: LocalHttpHardeningConfig) -> bool:
    if origin == "null":
        return bool(config.allow_null_origin)

    parsed = urlsplit(origin)
    scheme = (parsed.scheme or "").lower()
    hostname = (parsed.hostname or "").lower()
    port = parsed.port
    if not scheme or not hostname:
        return False

    for allowed in config.allowed_origins:
        if allowed.scheme != scheme:
            continue
        if allowed.hostname != hostname:
            continue
        if allowed.port is None:
            return True
        if port == allowed.port:
            return True
    return False


def _parse_host_header(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    parsed = urlsplit(f"//{raw}")
    return parsed.hostname.lower() if parsed.hostname else None


def _is_exempt_from_local_hardening(*, method: str, path: str) -> bool:
    upper_method = (method or "").upper()
    if upper_method == "OPTIONS":
        return True

    normalized_path = (path or "").rstrip("/") or "/"
    if upper_method == "GET" and normalized_path == "/healthz":
        return True

    # Exempt all well-known discovery endpoints (including base-path mounted variants).
    if upper_method == "GET" and "/.well-known/" in normalized_path:
        return True

    return False


class LocalHttpHardeningMiddleware:
    """Local HTTP hardening middleware for the 8080 MCP-over-HTTP surface (ADR-0014)."""

    def __init__(self, app: Any, *, config: LocalHttpHardeningConfig) -> None:
        self.app = app
        self._config = config

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method") or "")
        path = str(scope.get("path") or "")
        if _is_exempt_from_local_hardening(method=method, path=path):
            await self.app(scope, receive, send)
            return

        headers = _http_headers(scope)

        origin = (headers.get("origin") or "").strip()
        # Allow empty/missing origin when allow_null_origin is True (for server-to-server calls)
        origin_allowed = (
            (not origin and self._config.allow_null_origin)
            or (origin and _is_allowed_origin(origin=origin, config=self._config))
        )
        if not origin_allowed:
            response = JSONResponse(
                {"error": "origin_not_allowed", "origin": origin},
                status_code=403,
            )
            await response(scope, receive, send)
            return

        host = _parse_host_header(headers.get("host") or "")
        if not host or host not in self._config.allowed_hosts:
            response = JSONResponse(
                {"error": "host_not_allowed", "host": headers.get("host") or ""},
                status_code=403,
            )
            await response(scope, receive, send)
            return

        x_forwarded_host_raw = headers.get("x-forwarded-host") or ""
        if x_forwarded_host_raw:
            first = x_forwarded_host_raw.split(",", 1)[0].strip()
            forwarded_host = _parse_host_header(first)
            if not forwarded_host or forwarded_host not in self._config.allowed_hosts:
                response = JSONResponse(
                    {
                        "error": "host_not_allowed",
                        "host": headers.get("host") or "",
                        "x_forwarded_host": first,
                    },
                    status_code=403,
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
