from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from starlette.responses import Response

from ..http_base_path import detect_base_path
from ..http_oauth_metadata import PROTECTED_RESOURCE_METADATA_PATH


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


def _resource_metadata_path(headers: Mapping[str, str]) -> str:
    base_path = detect_base_path(
        _env("GSD_HTTP_BASE_PATH"),
        headers.get("x-forwarded-prefix"),
    )
    if base_path == "/":
        return PROTECTED_RESOURCE_METADATA_PATH
    return f"{base_path}{PROTECTED_RESOURCE_METADATA_PATH}"


def _extract_scopes_from_claims(claims: Mapping[str, Any]) -> set[str]:
    raw = claims.get("scope")
    if isinstance(raw, str):
        return {part for part in raw.split() if part}

    raw = claims.get("scp")
    if isinstance(raw, str):
        return {part for part in raw.split() if part}

    if isinstance(raw, list):
        if not all(isinstance(value, str) for value in raw):
            return set()
        return {value.strip() for value in raw if value.strip()}

    return set()


_EXECUTE_TOOLS: set[str] = {
    "web_eval_agent",
    "web_task_agent",
    "web_task_agent_github",
    "setup_browser_state",
}
_READ_TOOLS: set[str] = {
    "get_screenshots",
    "get_run_events",
}

_SCOPE_EXECUTE = "gsd:browser:execute"
_SCOPE_READ = "gsd:browser:read"
_SCOPE_ADMIN = "gsd:admin"

_SCOPE_STRING_EXECUTE_OR_ADMIN = f"{_SCOPE_EXECUTE} {_SCOPE_ADMIN}"
_SCOPE_STRING_READ_OR_ADMIN = f"{_SCOPE_READ} {_SCOPE_ADMIN}"


def _required_scope_string_for_mcp_payload(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None

    raw_method = payload.get("method")
    if not isinstance(raw_method, str):
        return None

    method = raw_method.strip()
    if method == "tools/call":
        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
        tool_name = params.get("name") if isinstance(params.get("name"), str) else ""
        if tool_name in _EXECUTE_TOOLS:
            return _SCOPE_STRING_EXECUTE_OR_ADMIN
        if tool_name in _READ_TOOLS:
            return _SCOPE_STRING_READ_OR_ADMIN
        return None

    if method in {"tasks/get", "tasks/result"}:
        return _SCOPE_STRING_READ_OR_ADMIN
    if method == "tasks/cancel":
        return _SCOPE_STRING_EXECUTE_OR_ADMIN

    return None


def _has_required_scope(*, required: str, scopes: set[str]) -> bool:
    required_set = set(required.split())
    return bool(required_set.intersection(scopes))


def _http_headers(scope: Mapping[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in scope.get("headers") or []:
        try:
            headers[key.decode("latin-1").lower()] = value.decode("latin-1")
        except Exception:  # noqa: BLE001
            continue
    return headers


async def _read_body(receive: Callable[[], Awaitable[dict[str, Any]]]) -> bytes:
    chunks: list[bytes] = []
    more_body = True
    while more_body:
        message = await receive()
        if message.get("type") != "http.request":
            continue
        body = message.get("body", b"") or b""
        if body:
            chunks.append(body)
        more_body = bool(message.get("more_body"))
    return b"".join(chunks)


def _replay_receive(body: bytes) -> Callable[[], Awaitable[dict[str, Any]]]:
    sent = False

    async def _receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return _receive


class HttpAuthMiddleware:
    """HTTP auth + scope enforcement for the MCP /mcp HTTP surface.

    This middleware enforces the baseline challenge semantics pinned in the canonical spec:
    - 401 (missing/invalid token) with `resource_metadata=...`
    - 403 (authenticated but insufficient scope) with `error=\"insufficient_scope\"`

    Wrong-audience explicit handling is intentionally deferred (task I5.3b).
    """

    def __init__(self, app: Any, *, verifier: Any) -> None:
        self.app = app
        self._verifier = verifier

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "")
        method = str(scope.get("method") or "").upper()
        normalized_path = path.rstrip("/") or "/"
        if normalized_path != "/mcp":
            await self.app(scope, receive, send)
            return

        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        headers = _http_headers(scope)
        token = _authorization_bearer_token(headers)
        if not token:
            challenge = f'Bearer resource_metadata="{_resource_metadata_path(headers)}"'
            response = Response(status_code=401, headers={"WWW-Authenticate": challenge})
            await response(scope, receive, send)
            return

        access_token = await self._verifier.verify_token(token)
        if access_token is None:
            challenge = f'Bearer resource_metadata="{_resource_metadata_path(headers)}"'
            response = Response(status_code=401, headers={"WWW-Authenticate": challenge})
            await response(scope, receive, send)
            return

        body = await _read_body(receive)
        receive = _replay_receive(body)

        required_scope_string: str | None = None
        try:
            payload = json.loads(body.decode("utf-8")) if body else None
        except Exception:  # noqa: BLE001
            payload = None

        if payload is not None:
            required_scope_string = _required_scope_string_for_mcp_payload(payload)

        if required_scope_string:
            scopes = _extract_scopes_from_claims(getattr(access_token, "claims", {}) or {})
            if not _has_required_scope(required=required_scope_string, scopes=scopes):
                challenge = (
                    'Bearer error="insufficient_scope", '
                    f'scope="{required_scope_string}"'
                )
                response = Response(status_code=403, headers={"WWW-Authenticate": challenge})
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
