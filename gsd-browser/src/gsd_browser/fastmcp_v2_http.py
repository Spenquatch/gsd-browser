"""FastMCP v2 HTTP (ASGI) entrypoint.

This is gated by `GSD_TRANSPORT=http`. In stdio mode, this module does not create an ASGI app.

JWT verification and identity mapping are implemented in later tasks; this entrypoint only
enforces fail-fast configuration presence for HTTP mode.
"""

from __future__ import annotations

import os

from fastmcp.server.server import StarletteWithLifespan

from .fastmcp_v2_stdio import mcp

_REQUIRED_JWT_ENV_VARS: tuple[str, ...] = (
    "GSD_JWT_JWKS_URL",
    "GSD_JWT_ISSUER",
    "GSD_JWT_AUDIENCE",
)


def _env(name: str) -> str:
    return str(os.environ.get(name, "")).strip()


def _require_env(name: str) -> str:
    value = _env(name)
    if not value:
        raise RuntimeError(f"Missing required env var for HTTP transport: {name}")
    return value


def _transport() -> str:
    return _env("GSD_TRANSPORT").lower() or "stdio"


def build_http_app() -> StarletteWithLifespan:
    """Build the ASGI app for HTTP transport.

    Requirements (canonical spec):
    - Only valid when `GSD_TRANSPORT=http`
    - Refuse to start unless JWT config is present
    """

    transport = _transport()
    if transport != "http":
        raise RuntimeError("HTTP entrypoint is only valid when GSD_TRANSPORT=http")

    for name in _REQUIRED_JWT_ENV_VARS:
        _require_env(name)

    # Use FastMCP's "streamable-http" transport (FastMCP v2).
    return mcp.http_app(transport="streamable-http")


app: StarletteWithLifespan | None = build_http_app() if _transport() == "http" else None

