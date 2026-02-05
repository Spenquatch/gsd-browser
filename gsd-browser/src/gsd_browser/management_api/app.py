from __future__ import annotations

import base64
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
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
from ..optionb.task_ownership import TaskOwnershipRecord

logger = logging.getLogger("gsd_browser.management_api")

_ModelT = TypeVar("_ModelT")


def _env(name: str) -> str:
    return str(os.environ.get(name, "")).strip()


def _stream_base_url_from_env() -> str | None:
    host = _env("GSD_STREAMING_PUBLIC_HOST")
    if not host:
        return None

    scheme = (_env("GSD_STREAMING_PUBLIC_SCHEME") or "wss").strip().lower()
    if scheme == "wss":
        scheme = "https"
    elif scheme == "ws":
        scheme = "http"

    return f"{scheme}://{host}"


def _require_uuid4(value: str, *, name: str) -> str:
    raw = str(value or "").strip()
    try:
        parsed = uuid.UUID(raw)
    except (TypeError, ValueError) as exc:
        raise OpsTasksServiceError(
            code=f"invalid_{name}",
            message=f"Invalid {name}",
            details={},
        ) from exc
    if parsed.version != 4:
        raise OpsTasksServiceError(
            code=f"invalid_{name}",
            message=f"Invalid {name}",
            details={},
        )
    return raw


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


def _unauthorized_response(*, reason: str, details: dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": "unauthenticated",
                "message": "Missing or invalid authentication",
                "details": {"reason": reason, **(details or {})},
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
    """Auth middleware for the 8081 management REST API (JWT and X-API-Key)."""

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
                    response = _unauthorized_response(reason="invalid_api_key")
                    await response(scope, receive, send)
                    return
                identity, scopes = match
                scope["gsd.identity"] = identity
                scope["gsd.scopes"] = scopes
                await self.app(scope, receive, send)
                return

        token = _authorization_bearer_token(headers)
        if not token:
            response = _unauthorized_response(reason="missing_bearer")
            await response(scope, receive, send)
            return

        if self._jwt_verifier is None:
            response = _unauthorized_response(reason="jwt_not_configured")
            await response(scope, receive, send)
            return

        audience_mismatch: Any | None = None
        if isinstance(self._jwt_verifier, GsdJwtVerifier):
            access_token, audience_mismatch = (
                await self._jwt_verifier.verify_token_with_audience_details(token)
            )
        else:
            access_token = await self._jwt_verifier.verify_token(token)

        if access_token is None:
            if audience_mismatch is not None:
                response = _unauthorized_response(
                    reason="audience_mismatch",
                    details={
                        "expected_audience": getattr(audience_mismatch, "expected_audience", ""),
                        "actual_audience": getattr(audience_mismatch, "actual_audience", ""),
                    },
                )
            else:
                response = _unauthorized_response(reason="invalid_bearer")
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
            response = _unauthorized_response(
                reason="invalid_claims",
                details={
                    "hint": (
                        "Expected tenant/subject claims. "
                        "If using Clerk, ensure the JWT template is configured "
                        "(or org claims are present)."
                    )
                },
            )
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


def _now_ms() -> int:
    return int(time.time() * 1000)


def _parse_iso_datetime_to_epoch_s(raw: bytes) -> int | None:
    try:
        value = raw.decode("utf-8").strip()
        if not value:
            return None
        if value.endswith("Z"):
            value = f"{value[:-1]}+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return int(dt.astimezone(UTC).timestamp())
    except Exception:  # noqa: BLE001
        return None


def _task_state_from_runs_hash(runs_hash: dict[bytes, bytes]) -> tuple[str, int | None]:
    raw_state = runs_hash.get(b"state")
    state = raw_state.decode("utf-8") if isinstance(raw_state, (bytes, bytearray)) else ""

    if state in {"running"}:
        status = "running"
    elif state in {"completed"}:
        status = "completed"
    elif state in {"failed"}:
        status = "failed"
    elif state in {"cancelled"}:
        status = "cancelled"
    else:
        status = "queued"

    last_activity: int | None = None
    for key in (b"completed_at", b"started_at"):
        raw_dt = runs_hash.get(key)
        if raw_dt is None:
            continue
        parsed = _parse_iso_datetime_to_epoch_s(raw_dt)
        if parsed is not None:
            last_activity = parsed
            break

    return status, last_activity


async def _read_task_ownership_records(
    *,
    docket: Docket,
    identity: Identity,
    now_ms: int,
    session_id: str | None = None,
) -> list[TaskOwnershipRecord]:
    import redis.exceptions

    pattern = "gsd:v1:tasks:*:owner"
    records: list[TaskOwnershipRecord] = []

    try:
        async with docket.redis() as redis:
            cursor = 0
            while True:
                cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=250)
                if keys:
                    raw_values = await redis.mget(keys)
                    for raw in raw_values:
                        if raw is None:
                            continue
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8")
                        if not isinstance(raw, str):
                            continue
                        try:
                            record = TaskOwnershipRecord.model_validate_json(raw)
                        except Exception:  # noqa: BLE001
                            continue
                        if (
                            record.tenant_id != identity.tenant_id
                            or record.subject_id != identity.subject_id
                        ):
                            continue
                        if int(record.expires_at_ms) <= int(now_ms):
                            continue
                        if session_id is not None and record.session_id != session_id:
                            continue
                        records.append(record)
                if cursor == 0:
                    break
    except redis.exceptions.RedisError as exc:
        raise RuntimeError("Failed to list TaskOwnershipRecords") from exc

    return records


async def _sessions_payload(
    *, docket: Docket, identity: Identity, session_id: str | None = None
) -> list[dict[str, Any]]:
    now_ms = _now_ms()
    stream_base_url = _stream_base_url_from_env()
    records = await _read_task_ownership_records(
        docket=docket,
        identity=identity,
        now_ms=now_ms,
        session_id=session_id,
    )
    if not records:
        return []

    from fastmcp.server.tasks.keys import build_task_key

    by_session: dict[str, dict[str, Any]] = {}

    import redis.exceptions

    try:
        async with docket.redis() as redis:
            for record in records:
                sid = record.session_id
                created_at_s = int(int(record.created_at_ms) / 1000)

                agg = by_session.get(sid)
                if agg is None:
                    agg = {
                        "session_id": sid,
                        "status": "create",
                        "tenant_id": record.tenant_id,
                        "subject_id": record.subject_id,
                        "worker_id": record.worker_id or "",
                        "stream_url": stream_base_url,
                        "created_at": created_at_s,
                        "last_activity_at": created_at_s,
                        "_task_states": set(),
                    }
                    by_session[sid] = agg
                else:
                    if created_at_s < int(agg["created_at"]):
                        agg["created_at"] = created_at_s
                    if created_at_s > int(agg["last_activity_at"]):
                        agg["last_activity_at"] = created_at_s

                task_key = build_task_key(
                    record.session_id, record.task_id, "tool", record.tool_name
                )
                runs_hash = await redis.hgetall(docket.runs_key(task_key))
                if runs_hash:
                    state, last_activity_s = _task_state_from_runs_hash(runs_hash)
                else:
                    state, last_activity_s = ("queued", None)

                agg["_task_states"].add(state)
                if (
                    last_activity_s is not None
                    and last_activity_s > int(agg["last_activity_at"])
                ):
                    agg["last_activity_at"] = last_activity_s
    except redis.exceptions.RedisError as exc:
        raise RuntimeError("Failed to list session state") from exc

    out: list[dict[str, Any]] = []
    for agg in by_session.values():
        states = cast(set[str], agg.pop("_task_states"))
        if "running" in states:
            agg["status"] = "active"
        elif "queued" in states:
            agg["status"] = "create"
        else:
            agg["status"] = "terminated"
        out.append(agg)

    out.sort(
        key=lambda s: (int(s.get("created_at", 0)), str(s.get("session_id", ""))),
        reverse=True,
    )
    return out


async def _list_sessions(request: Request) -> Response:
    identity, scopes = _require_identity_and_scopes(request)
    try:
        _require_ops_scopes(scopes, required=("gsd:browser:read", "gsd:admin"))

        docket = cast(Docket, request.app.state.docket)
        with _docket_scope(docket):
            sessions = await _sessions_payload(docket=docket, identity=identity)
        return JSONResponse(sessions)
    except OpsTasksServiceError as exc:
        status_code = 403 if exc.code == "forbidden" else 400
        return _error_response(
            status_code=status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


async def _get_session(request: Request) -> Response:
    identity, scopes = _require_identity_and_scopes(request)
    try:
        _require_ops_scopes(scopes, required=("gsd:browser:read", "gsd:admin"))
        session_id = str(request.path_params.get("session_id") or "").strip()
        if not session_id:
            raise OpsTasksServiceError(
                code="invalid_session_id",
                message="Invalid session_id",
                details={},
            )

        docket = cast(Docket, request.app.state.docket)
        with _docket_scope(docket):
            sessions = await _sessions_payload(
                docket=docket, identity=identity, session_id=session_id
            )
        if not sessions:
            return _error_response(
                status_code=404,
                code="not_found",
                message="Session not found",
                details={},
            )
        return JSONResponse(sessions[0])
    except OpsTasksServiceError as exc:
        status_code = 403 if exc.code == "forbidden" else 400
        return _error_response(
            status_code=status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


async def _list_session_screenshots(request: Request) -> Response:
    identity, scopes = _require_identity_and_scopes(request)
    try:
        _require_ops_scopes(scopes, required=("gsd:browser:read", "gsd:admin"))
        session_id = _require_uuid4(
            str(request.path_params.get("session_id") or ""), name="session_id"
        )

        def _truthy(raw: str) -> bool:
            return str(raw or "").strip().lower() in {"1", "true", "yes", "y"}

        params = request.query_params
        last_n_raw = params.get("last_n") or params.get("limit") or "10"
        try:
            last_n = int(last_n_raw)
        except ValueError:
            last_n = 10
        last_n = min(max(last_n, 0), 20)

        screenshot_type = (
            params.get("type") or params.get("screenshot_type") or "agent_step"
        ).strip().lower()
        if screenshot_type not in {"agent_step", "stream_sample", "all"}:
            screenshot_type = "agent_step"

        include_data = _truthy(params.get("include_data") or "false")

        docket = cast(Docket, request.app.state.docket)
        with _docket_scope(docket):
            from ..optionb.artifact_index import get_artifact_index_store

            store = get_artifact_index_store()
            zset_key = (
                f"gsd:v1:tenants:{identity.tenant_id}:subjects:{identity.subject_id}"
                f":sessions:{session_id}:screenshots:z"
            )
            candidate_limit = min(max(last_n * 10, 50), 200)

            import redis.exceptions

            async with docket.redis() as redis:
                candidates = await redis.zrevrange(zset_key, 0, candidate_limit - 1)

                out: list[dict[str, Any]] = []
                for raw in candidates:
                    artifact_id = (
                        raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                    )
                    try:
                        parsed = uuid.UUID(str(artifact_id))
                    except (TypeError, ValueError):
                        continue
                    if parsed.version != 4:
                        continue

                    record = await store.get_meta(artifact_id)
                    if record is None or record.state != "ready":
                        continue
                    if record.artifact_kind != "screenshot":
                        continue
                    if (
                        screenshot_type != "all"
                        and record.screenshot_type != screenshot_type
                    ):
                        continue

                    data_base64: str | None = None
                    if include_data and str(record.s3_bucket).strip().lower() == "redis":
                        try:
                            blob = await redis.get(str(record.s3_key))
                        except redis.exceptions.RedisError:
                            blob = None
                        if isinstance(blob, bytes) and blob:
                            data_base64 = base64.b64encode(blob).decode("ascii")

                    out.append(
                        {
                            "artifact_id": record.artifact_id,
                            "timestamp": float(record.created_at_ms) / 1000.0,
                            "type": record.screenshot_type,
                            "step": record.step,
                            "url": record.page_url,
                            "has_error": bool(record.has_error),
                            "mime_type": record.content_type,
                            "size_bytes": int(record.size_bytes),
                            "data_base64": data_base64,
                        }
                    )
                    if len(out) >= last_n:
                        break

        return JSONResponse(
            {
                "session_id": session_id,
                "filters": {
                    "last_n": last_n,
                    "screenshot_type": screenshot_type,
                    "include_data": include_data,
                },
                "screenshots": out,
            }
        )
    except OpsTasksServiceError as exc:
        status_code = 403 if exc.code == "forbidden" else 400
        return _error_response(
            status_code=status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )


async def _terminate_session(request: Request) -> Response:
    identity, scopes = _require_identity_and_scopes(request)
    try:
        _require_ops_scopes(scopes, required=("gsd:browser:execute", "gsd:admin"))
        session_id = str(request.path_params.get("session_id") or "").strip()
        if not session_id:
            raise OpsTasksServiceError(
                code="invalid_session_id",
                message="Invalid session_id",
                details={},
            )

        docket = cast(Docket, request.app.state.docket)
        with _docket_scope(docket):
            now_ms = _now_ms()
            records = await _read_task_ownership_records(
                docket=docket, identity=identity, now_ms=now_ms, session_id=session_id
            )
            if not records:
                return _error_response(
                    status_code=404,
                    code="not_found",
                    message="Session not found",
                    details={},
                )

            from fastmcp.server.tasks.keys import build_task_key

            cancelled = 0
            errors: list[str] = []
            for record in records:
                try:
                    task_key = build_task_key(
                        record.session_id,
                        record.task_id,
                        "tool",
                        record.tool_name,
                    )
                    await docket.cancel(task_key)
                    cancelled += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(str(exc)[:200])

        return JSONResponse(
            {
                "ok": True,
                "session_id": session_id,
                "cancelled_tasks": cancelled,
                "errors": errors,
            }
        )
    except OpsTasksServiceError as exc:
        status_code = 403 if exc.code == "forbidden" else 400
        return _error_response(
            status_code=status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
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
            Route("/api/v1/sessions", _list_sessions, methods=["GET"]),
            Route("/api/v1/sessions/{session_id:str}", _get_session, methods=["GET"]),
            Route(
                "/api/v1/sessions/{session_id:str}/screenshots",
                _list_session_screenshots,
                methods=["GET"],
            ),
            Route(
                "/api/v1/sessions/{session_id:str}/terminate",
                _terminate_session,
                methods=["POST"],
            ),
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
