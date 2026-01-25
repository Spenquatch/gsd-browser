from __future__ import annotations

import os
from typing import Any

from fastmcp.server.server import StarletteWithLifespan
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .http_base_path import detect_base_path, normalize_base_path

PROTECTED_RESOURCE_METADATA_PATH = "/.well-known/oauth-protected-resource"

SCOPES_SUPPORTED: list[str] = [
    "gsd:browser:execute",
    "gsd:browser:read",
    "gsd:admin",
]

BEARER_METHODS_SUPPORTED: list[str] = ["header"]


def _env(name: str) -> str:
    return str(os.environ.get(name, "")).strip()


def _require_env(name: str) -> str:
    value = _env(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def detect_request_base_path(request: Request) -> str:
    return detect_base_path(
        _env("GSD_HTTP_BASE_PATH"),
        request.headers.get("x-forwarded-prefix"),
    )


def resource_metadata_path_for_base_path(base_path: str) -> str:
    normalized = normalize_base_path(base_path)
    if normalized == "/":
        return PROTECTED_RESOURCE_METADATA_PATH
    return f"{normalized}{PROTECTED_RESOURCE_METADATA_PATH}"


def resource_metadata_path_for_request(request: Request) -> str:
    return resource_metadata_path_for_base_path(detect_request_base_path(request))


def build_protected_resource_metadata_payload(*, audience: str, issuer: str) -> dict[str, Any]:
    return {
        "resource": str(audience),
        "authorization_servers": [str(issuer)],
        "scopes_supported": list(SCOPES_SUPPORTED),
        "bearer_methods_supported": list(BEARER_METHODS_SUPPORTED),
    }


def _metadata_response() -> JSONResponse:
    payload = build_protected_resource_metadata_payload(
        audience=_require_env("GSD_JWT_AUDIENCE"),
        issuer=_require_env("GSD_JWT_ISSUER"),
    )
    return JSONResponse(payload)


async def oauth_protected_resource_root(_: Request) -> Response:
    return _metadata_response()


async def oauth_protected_resource_under_base_path(request: Request) -> Response:
    detected = detect_request_base_path(request)
    if detected == "/":
        return Response(status_code=404)

    prefix = request.path_params.get("base_path")
    candidate = normalize_base_path(str(prefix or ""))
    if candidate != detected:
        return Response(status_code=404)

    return _metadata_response()


def mount_oauth_protected_resource_metadata_routes(app: StarletteWithLifespan) -> None:
    app.add_route(
        PROTECTED_RESOURCE_METADATA_PATH,
        oauth_protected_resource_root,
        methods=["GET"],
        name="oauth_protected_resource_metadata_root",
    )
    app.add_route(
        f"/{{base_path:path}}{PROTECTED_RESOURCE_METADATA_PATH}",
        oauth_protected_resource_under_base_path,
        methods=["GET"],
        name="oauth_protected_resource_metadata_base_path",
    )
