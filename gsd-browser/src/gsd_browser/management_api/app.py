from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from typing import Any, TypeVar, cast

import fastmcp
from docket import Docket
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ..optionb.api_keys import ApiKeyRegistry, load_api_key_registry_from_env
from ..optionb.http_hardening import (
    LocalHttpHardeningMiddleware,
    load_local_http_hardening_config_from_env,
)
from ..optionb.identity import (
    GsdJwtVerifier,
    Identity,
    get_jwt_subject_id_claim_name,
    get_jwt_tenant_id_claim_name,
    identity_from_claims,
)
from ..optionb.ops_jobs import OpsJobsServiceError, get_ops_jobs_service
from ..optionb.ops_tasks import (
    OpsAdminTasksListQuery,
    OpsTasksListQuery,
    OpsTasksServiceError,
    get_ops_tasks_service,
)
from ..optionb.scopes import extract_scopes_from_claims, has_any_scope

logger = logging.getLogger("gsd_browser.management_api")

_ModelT = TypeVar("_ModelT")


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


@asynccontextmanager
async def _docket_lifespan(app: Starlette) -> Iterator[None]:
    docket = Docket(
        name=str(fastmcp.settings.docket.name or "fastmcp"),
        url=str(fastmcp.settings.docket.url),
    )
    async with docket:
        app.state.docket = docket
        try:
            yield
        finally:
            try:
                delattr(app.state, "docket")
            except Exception:  # noqa: BLE001
                pass


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": str(code),
                "message": str(message),
                "details": details or {},
            }
        },
        status_code=int(status_code),
    )


def _admin_mode_enabled() -> bool:
    return _env("GSD_ADMIN_MODE") == "1"


def _require_identity_and_scopes(request: Request) -> tuple[Identity, set[str]]:
    identity = request.scope.get("gsd.identity")
    scopes = request.scope.get("gsd.scopes")
    if not isinstance(identity, Identity) or not isinstance(scopes, set):
        # Should not happen: middleware is responsible for authentication.
        raise RuntimeError("Missing identity/scopes in management request scope")
    return identity, scopes


def _parse_query_model(model: type[_ModelT], request: Request) -> _ModelT:
    try:
        return model.model_validate(dict(request.query_params))
    except ValidationError as exc:
        raise OpsTasksServiceError(
            code="invalid_query",
            message="Invalid query",
            details={"errors": exc.errors()},
        ) from exc


@contextmanager
def _docket_scope(docket: Docket) -> Iterator[None]:
    from fastmcp.server.dependencies import _current_docket

    token = _current_docket.set(docket)
    try:
        yield
    finally:
        _current_docket.reset(token)


def _require_ops_scopes(scopes: set[str], *, required: tuple[str, ...]) -> None:
    if has_any_scope(scopes, required):
        return
    raise OpsTasksServiceError(
        code="forbidden",
        message="Insufficient scope",
        details={"required_scopes": list(required)},
    )


async def _list_tasks(request: Request) -> Response:
    identity, scopes = _require_identity_and_scopes(request)
    try:
        _require_ops_scopes(scopes, required=("gsd:browser:read", "gsd:admin"))

        query = _parse_query_model(OpsTasksListQuery, request)
        docket = cast(Docket, request.app.state.docket)
        with _docket_scope(docket):
            service = get_ops_tasks_service()
            response = await service.list_tasks(identity=identity, query=query)
        return JSONResponse(response.model_dump(mode="json"))
    except OpsTasksServiceError as exc:
        status_code = 403 if exc.code == "forbidden" else 400
        return _error_response(
            status_code=status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


async def _admin_list_tasks(request: Request) -> Response:
    identity, scopes = _require_identity_and_scopes(request)
    try:
        _require_ops_scopes(scopes, required=("gsd:admin",))
        if not _admin_mode_enabled():
            logger.warning(
                "audit.admin_api_access_denied",
                extra={
                    "endpoint": "/api/v1/admin/tasks",
                    "reason": "admin_mode_disabled",
                    "caller_tenant_id": identity.tenant_id,
                    "caller_subject_id": identity.subject_id,
                    "caller_transport": identity.transport,
                },
            )
            raise OpsTasksServiceError(
                code="forbidden",
                message="Admin endpoints are disabled",
                details={},
            )

        logger.info(
            "audit.admin_task_list",
            extra={
                "endpoint": "/api/v1/admin/tasks",
                "caller_tenant_id": identity.tenant_id,
                "caller_subject_id": identity.subject_id,
                "caller_transport": identity.transport,
            },
        )

        query = _parse_query_model(OpsAdminTasksListQuery, request)
        docket = cast(Docket, request.app.state.docket)
        with _docket_scope(docket):
            service = get_ops_tasks_service()
            response = await service.admin_list_tasks(query=query)
        return JSONResponse(response.model_dump(mode="json"))
    except OpsTasksServiceError as exc:
        status_code = 403 if exc.code == "forbidden" else 400
        return _error_response(
            status_code=status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


async def _get_job(request: Request) -> Response:
    identity, scopes = _require_identity_and_scopes(request)
    try:
        _require_ops_scopes(scopes, required=("gsd:browser:read", "gsd:admin"))

        job_id = str(request.path_params.get("job_id") or "")
        docket = cast(Docket, request.app.state.docket)
        with _docket_scope(docket):
            service = get_ops_jobs_service()
            response = await service.get_job(identity=identity, job_id=job_id)

        if response is None:
            return _error_response(
                status_code=404,
                code="not_found",
                message="Not found",
                details={},
            )

        return JSONResponse(response.model_dump(mode="json"))
    except OpsJobsServiceError as exc:
        return _error_response(
            status_code=400,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
    except OpsTasksServiceError as exc:
        status_code = 403 if exc.code == "forbidden" else 400
        return _error_response(
            status_code=status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


async def _admin_get_job(request: Request) -> Response:
    identity, scopes = _require_identity_and_scopes(request)
    try:
        _require_ops_scopes(scopes, required=("gsd:admin",))
        if not _admin_mode_enabled():
            logger.warning(
                "audit.admin_api_access_denied",
                extra={
                    "endpoint": "/api/v1/admin/jobs/{job_id}",
                    "reason": "admin_mode_disabled",
                    "caller_tenant_id": identity.tenant_id,
                    "caller_subject_id": identity.subject_id,
                    "caller_transport": identity.transport,
                },
            )
            raise OpsTasksServiceError(
                code="forbidden",
                message="Admin endpoints are disabled",
                details={},
            )

        logger.info(
            "audit.admin_job_get",
            extra={
                "endpoint": "/api/v1/admin/jobs/{job_id}",
                "caller_tenant_id": identity.tenant_id,
                "caller_subject_id": identity.subject_id,
                "caller_transport": identity.transport,
            },
        )

        job_id = str(request.path_params.get("job_id") or "")
        docket = cast(Docket, request.app.state.docket)
        with _docket_scope(docket):
            service = get_ops_jobs_service()
            response = await service.admin_get_job(job_id=job_id)

        if response is None:
            return _error_response(
                status_code=404,
                code="not_found",
                message="Not found",
                details={},
            )

        return JSONResponse(response.model_dump(mode="json"))
    except OpsJobsServiceError as exc:
        return _error_response(
            status_code=400,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
    except OpsTasksServiceError as exc:
        status_code = 403 if exc.code == "forbidden" else 400
        return _error_response(
            status_code=status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


def build_management_app() -> Starlette:
    """Build the 8081 management REST API app (HTTP_API.md)."""

    app = Starlette(
        lifespan=_docket_lifespan,
        routes=[
            Route("/healthz", _healthz, methods=["GET"]),
            Route("/api/v1/tasks", _list_tasks, methods=["GET"]),
            Route("/api/v1/jobs/{job_id:str}", _get_job, methods=["GET"]),
            Route("/api/v1/admin/tasks", _admin_list_tasks, methods=["GET"]),
            Route("/api/v1/admin/jobs/{job_id:str}", _admin_get_job, methods=["GET"]),
        ]
    )

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
