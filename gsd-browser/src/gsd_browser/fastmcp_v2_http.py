"""FastMCP v2 HTTP (ASGI) entrypoint.

This is gated by `GSD_TRANSPORT=http`. In stdio mode, this module does not create an ASGI app.

JWT verification (JWKS + issuer + audience + exp) is required for HTTP mode and is enforced
via FastMCP's auth middleware.
"""

from __future__ import annotations

import os

from fastmcp.server.server import StarletteWithLifespan

from .fastmcp_v2_stdio import mcp


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

    from .optionb.task_backend import require_docket_redis_url

    _ = require_docket_redis_url()

    jwks_url = _require_env("GSD_JWT_JWKS_URL")
    issuer = _require_env("GSD_JWT_ISSUER")
    audience = _require_env("GSD_JWT_AUDIENCE")

    from .optionb.identity import (
        GsdJwtVerifier,
        get_jwt_subject_id_claim_name,
        get_jwt_tenant_id_claim_name,
    )

    mcp.auth = GsdJwtVerifier(
        jwks_uri=jwks_url,
        issuer=issuer,
        audience=audience,
        tenant_id_claim=get_jwt_tenant_id_claim_name(),
        subject_id_claim=get_jwt_subject_id_claim_name(),
    )

    # Use FastMCP's "streamable-http" transport (FastMCP v2).
    return mcp.http_app(transport="streamable-http")


app: StarletteWithLifespan | None = build_http_app() if _transport() == "http" else None
