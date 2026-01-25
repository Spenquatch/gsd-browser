from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ..optionb.api_keys import ApiKeyRegistry, load_api_key_registry_from_env
from ..optionb.http_hardening import (
    LocalHttpHardeningMiddleware,
    load_local_http_hardening_config_from_env,
)
from ..optionb.identity import (
    GsdJwtVerifier,
    get_jwt_subject_id_claim_name,
    get_jwt_tenant_id_claim_name,
    identity_from_claims,
)
from ..optionb.scopes import extract_scopes_from_claims


def _env(name: str) -> str:
    return str(os.environ.get(name, "")).strip()


def _authorization_bearer_token(headers: Mapping[str, str]) -> str | None:
    raw = headers.get("authorization")
    if not raw:
        return None

    scheme, _, rest = raw.partition(" ")
    if scheme.lower() != "bearer":
        return None

    token = rest.strip()
    return token or None


def _http_headers(scope: Mapping[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in scope.get("headers") or []:
        try:
            headers[key.decode("latin-1").lower()] = value.decode("latin-1")
        except Exception:  # noqa: BLE001
            continue
    return headers


def _should_authenticate_request(*, method: str, path: str) -> bool:
    upper_method = (method or "").upper()
    if upper_method == "OPTIONS":
        return False

    normalized_path = (path or "").rstrip("/") or "/"
    if normalized_path == "/healthz":
        return False

    return normalized_path.startswith("/api/") or normalized_path == "/api"


def _unauthorized_response() -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": "unauthenticated",
                "message": "Missing or invalid authentication",
                "details": {},
            }
        },
        status_code=401,
    )


def _optional_jwt_verifier() -> GsdJwtVerifier | None:
    jwks_url = _env("GSD_JWT_JWKS_URL")
    issuer = _env("GSD_JWT_ISSUER")
    audience = _env("GSD_JWT_AUDIENCE")
    if not (jwks_url and issuer and audience):
        return None

    return GsdJwtVerifier(
        jwks_uri=jwks_url,
        issuer=issuer,
        audience=audience,
        tenant_id_claim=get_jwt_tenant_id_claim_name(),
        subject_id_claim=get_jwt_subject_id_claim_name(),
    )


class ManagementAuthMiddleware:
    """Auth middleware for the 8081 management REST API (JWT and optional X-API-Key)."""

    def __init__(
        self,
        app: Any,
        *,
        jwt_verifier: Any | None,
        api_keys: ApiKeyRegistry | None,
    ) -> None:
        self.app = app
        self._jwt_verifier = jwt_verifier
        self._api_keys = api_keys

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
        if not _should_authenticate_request(method=method, path=path):
            await self.app(scope, receive, send)
            return

        headers = _http_headers(scope)

        if self._api_keys is not None:
            api_key = (headers.get("x-api-key") or "").strip()
            if api_key:
                match = self._api_keys.lookup_identity_and_scopes(api_key)
                if match is None:
                    response = _unauthorized_response()
                    await response(scope, receive, send)
                    return
                identity, scopes = match
                scope["gsd.identity"] = identity
                scope["gsd.scopes"] = scopes
                await self.app(scope, receive, send)
                return

        token = _authorization_bearer_token(headers)
        if not token or self._jwt_verifier is None:
            response = _unauthorized_response()
            await response(scope, receive, send)
            return

        access_token = await self._jwt_verifier.verify_token(token)
        if access_token is None:
            response = _unauthorized_response()
            await response(scope, receive, send)
            return

        claims = getattr(access_token, "claims", {}) or {}
        try:
            identity = identity_from_claims(
                claims,
                tenant_id_claim=get_jwt_tenant_id_claim_name(),
                subject_id_claim=get_jwt_subject_id_claim_name(),
            )
        except ValueError:
            response = _unauthorized_response()
            await response(scope, receive, send)
            return

        scopes = extract_scopes_from_claims(claims)
        scope["gsd.identity"] = identity
        scope["gsd.scopes"] = scopes
        await self.app(scope, receive, send)


async def _healthz(_: Any) -> Response:
    return JSONResponse({"status": "ok"})


def build_management_app() -> Starlette:
    """Build the 8081 management REST API app (HTTP_API.md)."""

    app = Starlette(routes=[Route("/healthz", _healthz, methods=["GET"])])

    app.add_middleware(
        ManagementAuthMiddleware,
        jwt_verifier=_optional_jwt_verifier(),
        api_keys=load_api_key_registry_from_env(),
    )

    app.add_middleware(
        LocalHttpHardeningMiddleware,
        config=load_local_http_hardening_config_from_env(),
    )

    return app


app = build_management_app()

