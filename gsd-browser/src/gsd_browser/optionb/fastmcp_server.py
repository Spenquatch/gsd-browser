from __future__ import annotations

import logging
import os
from typing import Any

import fastmcp
import mcp.types
from fastmcp import FastMCP
from fastmcp.exceptions import DisabledError, NotFoundError
from fastmcp.tools.tool import FunctionTool
from mcp.shared.exceptions import McpError
from mcp.types import INVALID_PARAMS, METHOD_NOT_FOUND, ErrorData

from . import task_ownership
from .identity import Identity
from .request_context import identity_scope
from .task_ttl_policy import TTLOutOfBoundsError, compute_effective_ttl_ms

logger = logging.getLogger("gsd_browser.optionb.fastmcp_server")


def _task_poll_interval_ms() -> int:
    raw = str(os.environ.get("GSD_TASK_POLL_INTERVAL_MS", "")).strip()
    if not raw:
        return 2000
    try:
        value = int(raw)
    except ValueError:
        return 2000
    return value if value > 0 else 2000


def _require_task_id(params: object | None) -> str:
    if params is None:
        raise McpError(
            ErrorData(code=INVALID_PARAMS, message="Missing required parameter: taskId")
        )
    task_id = getattr(params, "taskId", None)
    if not isinstance(task_id, str) or not task_id.strip():
        raise McpError(
            ErrorData(code=INVALID_PARAMS, message="Missing required parameter: taskId")
        )
    return task_id.strip()


def _raise_not_found(task_id: str) -> None:
    raise NotFoundError(f"Task {task_id} not found")


class GsdFastMCP(FastMCP[Any]):
    """FastMCP server with Option B task ownership enforcement."""

    def _resolve_identity_for_current_request(self) -> Identity:
        from fastmcp.server.dependencies import get_access_token

        from .identity import (
            STDIO_IDENTITY,
            get_jwt_subject_id_claim_name,
            get_jwt_tenant_id_claim_name,
            identity_from_claims,
        )

        access_token = get_access_token()
        if access_token is None:
            return STDIO_IDENTITY

        return identity_from_claims(
            access_token.claims,
            tenant_id_claim=get_jwt_tenant_id_claim_name(),
            subject_id_claim=get_jwt_subject_id_claim_name(),
        )

    async def _write_task_owner_or_fail(
        self,
        *,
        task_id: str,
        tool_name: str,
        ttl_ms: int,
        session_id: str,
    ) -> None:
        identity = self._resolve_identity_for_current_request()
        record = task_ownership.build_record(
            task_id=task_id,
            tool_name=tool_name,
            identity=identity,
            session_id=session_id,
            ttl_ms=ttl_ms,
        )
        store = task_ownership.get_task_ownership_store()
        try:
            await store.write(record)
        except Exception as exc:  # noqa: BLE001
            await self._cancel_task_best_effort(
                task_id=task_id, tool_name=tool_name, session_id=session_id
            )
            raise McpError(
                ErrorData(
                    code=mcp.types.INTERNAL_ERROR,
                    message="Failed to persist task ownership record",
                )
            ) from exc

    async def _cancel_task_best_effort(
        self, *, task_id: str, tool_name: str, session_id: str
    ) -> None:
        docket = getattr(self, "_docket", None)
        if docket is None:
            return
        try:
            from fastmcp.server.tasks.keys import build_task_key

            task_key = build_task_key(session_id, task_id, "tool", tool_name)
            await docket.cancel(task_key)
        except Exception:  # noqa: BLE001
            return

    async def _require_task_owner(self, task_id: str) -> task_ownership.TaskOwnershipRecord:
        from fastmcp.server.dependencies import _current_docket

        identity = self._resolve_identity_for_current_request()
        store = task_ownership.get_task_ownership_store()
        docket = getattr(self, "_docket", None)
        if docket is None:
            raise McpError(
                ErrorData(
                    code=mcp.types.INTERNAL_ERROR,
                    message="Docket is required for task ownership lookup",
                )
            )

        token = None
        if _current_docket.get() is None:
            token = _current_docket.set(docket)
        try:
            record = await store.get(task_id)
        finally:
            if token is not None:
                _current_docket.reset(token)
        if record is None:
            _raise_not_found(task_id)
        if record.tenant_id != identity.tenant_id or record.subject_id != identity.subject_id:
            logger.warning(
                "audit.task_access_denied",
                extra={
                    "task_id": task_id,
                    "caller_tenant_id": identity.tenant_id,
                    "caller_subject_id": identity.subject_id,
                    "caller_transport": identity.transport,
                    "owner_tenant_id": record.tenant_id,
                    "owner_subject_id": record.subject_id,
                    "owner_transport": record.transport,
                    "tool_name": record.tool_name,
                    "session_id": record.session_id,
                },
            )
            _raise_not_found(task_id)

        return record

    def _setup_task_protocol_handlers(self) -> None:  # noqa: D401
        """Register task protocol handlers with ownership enforcement."""
        from fastmcp.server.tasks.protocol import (
            tasks_cancel_handler,
            tasks_get_handler,
            tasks_result_handler,
        )
        from mcp.types import (
            CancelTaskRequest,
            GetTaskPayloadRequest,
            GetTaskRequest,
            ListTasksRequest,
            ServerResult,
        )

        async def handle_get_task(req: GetTaskRequest) -> ServerResult:
            with identity_scope(self._resolve_identity_for_current_request()):
                task_id = _require_task_id(req.params)
                record = await self._require_task_owner(task_id)
                params = req.params.model_dump(by_alias=True, exclude_none=True)
                request_ctx = self._mcp_server.request_context
                sentinel = object()
                original_session_id = getattr(request_ctx, "session_id", sentinel)
                request_ctx.session_id = record.session_id
                try:
                    result = await tasks_get_handler(self, params)
                finally:
                    if original_session_id is sentinel:
                        try:
                            delattr(request_ctx, "session_id")
                        except Exception:  # noqa: BLE001
                            pass
                    else:
                        request_ctx.session_id = original_session_id

                updated = result.model_copy(update={"pollInterval": _task_poll_interval_ms()})
                return ServerResult(updated)

        async def handle_get_task_result(req: GetTaskPayloadRequest) -> ServerResult:
            with identity_scope(self._resolve_identity_for_current_request()):
                task_id = _require_task_id(req.params)
                record = await self._require_task_owner(task_id)
                params = req.params.model_dump(by_alias=True, exclude_none=True)
                request_ctx = self._mcp_server.request_context
                sentinel = object()
                original_session_id = getattr(request_ctx, "session_id", sentinel)
                request_ctx.session_id = record.session_id
                try:
                    result = await tasks_result_handler(self, params)
                finally:
                    if original_session_id is sentinel:
                        try:
                            delattr(request_ctx, "session_id")
                        except Exception:  # noqa: BLE001
                            pass
                    else:
                        request_ctx.session_id = original_session_id

                return ServerResult(result)

        async def handle_list_tasks(req: ListTasksRequest) -> ServerResult:
            # `tasks/list` is intentionally unsupported to preserve non-enumerability semantics.
            # See ADR-0012.
            raise McpError(
                ErrorData(
                    code=METHOD_NOT_FOUND,
                    message="Method tasks/list is not supported",
                )
            )

        async def handle_cancel_task(req: CancelTaskRequest) -> ServerResult:
            with identity_scope(self._resolve_identity_for_current_request()):
                task_id = _require_task_id(req.params)
                record = await self._require_task_owner(task_id)
                params = req.params.model_dump(by_alias=True, exclude_none=True)
                request_ctx = self._mcp_server.request_context
                sentinel = object()
                original_session_id = getattr(request_ctx, "session_id", sentinel)
                request_ctx.session_id = record.session_id
                try:
                    result = await tasks_cancel_handler(self, params)
                finally:
                    if original_session_id is sentinel:
                        try:
                            delattr(request_ctx, "session_id")
                        except Exception:  # noqa: BLE001
                            pass
                    else:
                        request_ctx.session_id = original_session_id

                updated = result.model_copy(update={"pollInterval": _task_poll_interval_ms()})
                return ServerResult(updated)

        self._mcp_server.request_handlers[GetTaskRequest] = handle_get_task
        self._mcp_server.request_handlers[GetTaskPayloadRequest] = handle_get_task_result
        self._mcp_server.request_handlers[ListTasksRequest] = handle_list_tasks
        self._mcp_server.request_handlers[CancelTaskRequest] = handle_cancel_task

    async def _call_tool_mcp(
        self, key: str, arguments: dict[str, Any]
    ) -> (
        list[mcp.types.ContentBlock]
        | tuple[list[mcp.types.ContentBlock], dict[str, Any]]
        | mcp.types.CallToolResult
    ):
        logger.debug("[%s] call_tool %s with %s", self.name, key, arguments)

        async with fastmcp.server.context.Context(fastmcp=self):
            identity = self._resolve_identity_for_current_request()
            with identity_scope(identity):
                try:
                    task_meta = None
                    try:
                        ctx = self._mcp_server.request_context
                        if ctx.experimental.is_task:
                            task_meta = ctx.experimental.task_metadata
                    except (AttributeError, LookupError):
                        pass

                    tool = await self._get_tool_with_task_config(key)
                    if (
                        tool
                        and self._should_enable_component(tool)
                        and hasattr(tool, "task_config")
                    ):
                        task_mode = tool.task_config.mode  # type: ignore[union-attr]

                        if task_mode == "required" and not task_meta:
                            raise McpError(
                                ErrorData(
                                    code=METHOD_NOT_FOUND,
                                    message=f"Tool '{key}' requires task-augmented execution",
                                )
                            )

                        if task_meta and task_mode != "forbidden":
                            if isinstance(tool, FunctionTool):
                                from fastmcp.server.dependencies import get_context
                                from fastmcp.server.tasks.handlers import handle_tool_as_task

                                ctx = get_context()
                                session_id = ctx.session_id
                                client_ttl_ms = int(getattr(task_meta, "ttl", 0) or 0)

                                # Compute effective TTL using server-controlled policy
                                try:
                                    effective_ttl_ms = compute_effective_ttl_ms(
                                        tool_name=key,
                                        client_ttl_ms=client_ttl_ms if client_ttl_ms > 0 else None,
                                    )
                                except TTLOutOfBoundsError as exc:
                                    logger.warning(
                                        "task.ttl_rejected",
                                        extra={
                                            "tool_name": key,
                                            "requested_ttl_s": exc.requested_s,
                                            "min_ttl_s": exc.min_s,
                                            "max_ttl_s": exc.max_s,
                                        },
                                    )
                                    return mcp.types.CallToolResult(
                                        content=[
                                            mcp.types.TextContent(
                                                type="text",
                                                text=str(exc),
                                            )
                                        ],
                                        isError=True,
                                        _meta={
                                            "modelcontextprotocol.io/task": {
                                                "returned_immediately": True
                                            }
                                        },
                                    )

                                # Build task_meta_dict with server-computed TTL
                                task_meta_dict = task_meta.model_dump(exclude_none=True)
                                task_meta_dict["ttl"] = effective_ttl_ms

                                result = await handle_tool_as_task(
                                    self, key, arguments, task_meta_dict
                                )

                                meta = dict(result.meta or {})
                                task_payload = dict(meta.get("modelcontextprotocol.io/task") or {})
                                task_id = task_payload.get("taskId")
                                if isinstance(task_id, str) and task_id.strip():
                                    await self._write_task_owner_or_fail(
                                        task_id=task_id.strip(),
                                        tool_name=key,
                                        ttl_ms=effective_ttl_ms,
                                        session_id=session_id,
                                    )
                                    task_payload["pollInterval"] = _task_poll_interval_ms()
                                    meta["modelcontextprotocol.io/task"] = task_payload
                                    result.meta = meta

                                return result

                        if task_meta and task_mode == "forbidden":
                            return mcp.types.CallToolResult(
                                content=[
                                    mcp.types.TextContent(
                                        type="text",
                                        text=(
                                            f"Tool '{key}' does not support "
                                            "task-augmented execution"
                                        ),
                                    )
                                ],
                                isError=True,
                                _meta={
                                    "modelcontextprotocol.io/task": {
                                        "returned_immediately": True
                                    }
                                },
                            )

                    result = await self._call_tool_middleware(key, arguments)
                    return result.to_mcp_result()
                except DisabledError as exc:
                    raise NotFoundError(f"Unknown tool: {key}") from exc
                except NotFoundError as exc:
                    raise NotFoundError(f"Unknown tool: {key}") from exc
