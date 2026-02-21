"""FastMCP v2 (Option B) stdio entrypoint.

This module wires the existing tool implementations into `fastmcp` v2 without changing tool
semantics. It uses the Option B runtime (Redis/Valkey-backed Docket tasks + identity-scoped
authorization/ownership enforcement).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, TypeVar

from fastmcp import Context
from fastmcp.dependencies import Depends, Progress
from fastmcp.server.tasks import TaskConfig
from mcp.types import ImageContent, TextContent

from . import mcp_server as sdk_server
from .config import Settings
from .optionb.cancellation import propagate_cancelled_error
from .optionb.fastmcp_server import GsdFastMCP
from .optionb.progress import (
    cancel_pending_agent_steps,
    drain_pending_agent_steps,
    emit_last_agent_step_snapshot,
    task_progress_scope,
)
from .optionb.progress import (
    emit as emit_task_progress,
)

logger = logging.getLogger("gsd_browser.fastmcp_v2")

mcp = GsdFastMCP("gsd")

_PROGRESS_DEPENDENCY = Depends(Progress)
_TASK_PROGRESS_INIT_DELAY_S = 0.10
_TASK_PROGRESS_STEP_DRAIN_S = 0.10
_TASK_PROGRESS_DRAIN_TERMINAL_S = 0.20

T = TypeVar("T")

if TYPE_CHECKING:
    from .optionb.identity import Identity


def _json_text(payload: object) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]


def _terminal_phase_from_result(result: list[TextContent]) -> tuple[str, str]:
    status: str | None = None
    if result:
        first = result[0]
        try:
            payload = json.loads(getattr(first, "text", "") or "")
        except Exception:  # noqa: BLE001
            payload = None
        if isinstance(payload, dict):
            raw = payload.get("status")
            if isinstance(raw, str):
                status = raw

    if status == "failed":
        return "failed", "status=failed"
    if status in {"success", "partial"}:
        return "done", f"status={status}"
    return "done", f"status={status or 'unknown'}"


def _resolve_identity_from_access_token() -> Identity | None:
    from fastmcp.server.dependencies import get_access_token

    from .optionb.identity import (
        get_jwt_subject_id_claim_name,
        get_jwt_tenant_id_claim_name,
        identity_from_claims,
    )

    access_token = get_access_token()
    if access_token is None:
        return None

    return identity_from_claims(
        access_token.claims,
        tenant_id_claim=get_jwt_tenant_id_claim_name(),
        subject_id_claim=get_jwt_subject_id_claim_name(),
    )


def _resolve_identity_for_current_call() -> Identity:
    from .optionb.identity import STDIO_IDENTITY

    return _resolve_identity_from_access_token() or STDIO_IDENTITY


async def _resolve_identity_for_docket_execution() -> Identity | None:
    record = await _resolve_job_record_for_docket_execution()
    if record is None:
        return None
    try:
        from .optionb.identity import Identity

        return Identity(
            tenant_id=record.tenant_id,
            subject_id=record.subject_id,
            transport=record.transport,
        )
    except Exception:  # noqa: BLE001
        return None


async def _resolve_job_record_for_docket_execution():  # noqa: ANN001
    try:
        from docket.dependencies import Dependency as DocketDependency

        task_key = DocketDependency.execution.get().key
    except LookupError:
        return None

    try:
        from .optionb.job_store import get_job_store

        store = get_job_store()
        job_id = await store.get_job_id_for_task_key(str(task_key))
        if not job_id:
            return None
        return await store.get(job_id)
    except Exception:  # noqa: BLE001
        return None


async def _call_with_identity(
    fn: Callable[..., Awaitable[T]],
    /,
    **kwargs: object,
) -> T:
    from .optionb.identity import STDIO_IDENTITY, Identity
    from .optionb.request_context import identity_scope

    identity = _resolve_identity_from_access_token()
    job_record = None
    if identity is None:
        job_record = await _resolve_job_record_for_docket_execution()
        if job_record is not None:
            identity = Identity(
                tenant_id=job_record.tenant_id,
                subject_id=job_record.subject_id,
                transport=job_record.transport,
            )
    if identity is None:
        # stdio/dev fallback: allow tests/operators to override identity resolution
        # via `_resolve_identity_for_current_call()`.
        identity = _resolve_identity_for_current_call() or STDIO_IDENTITY
    with identity_scope(identity), sdk_server.session_id_scope(
        getattr(job_record, "session_id", None) if job_record is not None else None
    ):
        return await fn(**kwargs)


def _admin_mode_enabled() -> bool:
    raw = str(os.environ.get("GSD_ADMIN_MODE", "")).strip().lower()
    return raw in {"1", "true", "yes", "y"}


@contextmanager
def _docket_scope(ctx: Context | None) -> object:
    from fastmcp.server.dependencies import _current_docket

    docket = None
    if ctx is not None:
        try:
            docket = ctx.fastmcp.docket  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            docket = None

    token = None
    if docket is not None:
        token = _current_docket.set(docket)
    try:
        yield
    finally:
        if token is not None:
            _current_docket.reset(token)


def _require_http_scopes(*, required: tuple[str, ...]) -> None:
    from fastmcp.server.dependencies import get_access_token

    from .optionb.scopes import extract_scopes_from_claims, has_any_scope

    access_token = get_access_token()
    if access_token is None:
        return

    scopes = extract_scopes_from_claims(getattr(access_token, "claims", {}) or {})
    if has_any_scope(scopes, required):
        return

    raise PermissionError("insufficient_scope")


def apply_configured_tool_policy(*, settings: Settings) -> None:
    """Apply env/config-driven tool exposure policy before serving MCP."""

    from .mcp_tool_policy import (
        KNOWN_MCP_TOOLS,
        apply_tool_exposure_policy,
        compute_tool_exposure_policy,
    )

    policy = compute_tool_exposure_policy(
        known_tools=set(KNOWN_MCP_TOOLS),
        enabled_raw=getattr(settings, "mcp_enabled_tools", ""),
        disabled_raw=getattr(settings, "mcp_disabled_tools", ""),
    )
    if policy.unknown_requested:
        logger.warning(
            "unknown_mcp_tools_requested",
            extra={"unknown": sorted(policy.unknown_requested)},
        )
    apply_tool_exposure_policy(mcp=mcp, policy=policy)


@mcp.tool(name="web_eval_agent", task=TaskConfig(mode="required"))
async def web_eval_agent(
    url: str,
    task: str,
    ctx: Context | None = None,
    headless_browser: bool = True,
    mode: str | None = None,
    budget_s: float | None = None,
    max_steps: int | None = None,
    step_timeout_s: float | None = None,
    progress: Progress = _PROGRESS_DEPENDENCY,
) -> list[TextContent]:
    max_steps_value = int(max_steps) if max_steps is not None and int(max_steps) > 0 else None
    with (
        task_progress_scope(progress=progress, max_steps=max_steps_value),
        propagate_cancelled_error(),
    ):
        await asyncio.sleep(_TASK_PROGRESS_INIT_DELAY_S)
        await emit_task_progress(phase="init", step=None, note="starting")
        try:
            result = await _call_with_identity(
                sdk_server.web_eval_agent,
                url=url,
                task=task,
                ctx=ctx,  # type: ignore[arg-type]
                headless_browser=headless_browser,
                mode=mode,
                budget_s=budget_s,
                max_steps=max_steps,
                step_timeout_s=step_timeout_s,
            )
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None:
                current.uncancel()
            await cancel_pending_agent_steps(timeout_s=_TASK_PROGRESS_DRAIN_TERMINAL_S)
            await emit_task_progress(phase="cancelled", step=None, note="cancelled")
            raise
        except Exception as exc:  # noqa: BLE001
            await drain_pending_agent_steps(timeout_s=_TASK_PROGRESS_DRAIN_TERMINAL_S)
            await emit_task_progress(phase="failed", step=None, note=str(exc))
            await asyncio.sleep(_TASK_PROGRESS_DRAIN_TERMINAL_S)
            raise

        await drain_pending_agent_steps(timeout_s=_TASK_PROGRESS_DRAIN_TERMINAL_S)
        await emit_last_agent_step_snapshot()
        await asyncio.sleep(_TASK_PROGRESS_STEP_DRAIN_S)
        phase, note = _terminal_phase_from_result(result)
        await emit_task_progress(phase=phase, step=None, note=note)
        await asyncio.sleep(_TASK_PROGRESS_DRAIN_TERMINAL_S)
        return result


@mcp.tool(name="web_task_agent", task=TaskConfig(mode="required"))
async def web_task_agent(
    url: str,
    task: str,
    ctx: Context | None = None,
    headless_browser: bool = True,
    mode: str | None = None,
    budget_s: float | None = None,
    max_steps: int | None = None,
    step_timeout_s: float | None = None,
    progress: Progress = _PROGRESS_DEPENDENCY,
) -> list[TextContent]:
    max_steps_value = int(max_steps) if max_steps is not None and int(max_steps) > 0 else None
    with (
        task_progress_scope(progress=progress, max_steps=max_steps_value),
        propagate_cancelled_error(),
    ):
        await asyncio.sleep(_TASK_PROGRESS_INIT_DELAY_S)
        await emit_task_progress(phase="init", step=None, note="starting")
        try:
            result = await _call_with_identity(
                sdk_server.web_task_agent,
                url=url,
                task=task,
                ctx=ctx,  # type: ignore[arg-type]
                headless_browser=headless_browser,
                mode=mode,
                budget_s=budget_s,
                max_steps=max_steps,
                step_timeout_s=step_timeout_s,
            )
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None:
                current.uncancel()
            await cancel_pending_agent_steps(timeout_s=_TASK_PROGRESS_DRAIN_TERMINAL_S)
            await emit_task_progress(phase="cancelled", step=None, note="cancelled")
            raise
        except Exception as exc:  # noqa: BLE001
            await drain_pending_agent_steps(timeout_s=_TASK_PROGRESS_DRAIN_TERMINAL_S)
            await emit_task_progress(phase="failed", step=None, note=str(exc))
            await asyncio.sleep(_TASK_PROGRESS_DRAIN_TERMINAL_S)
            raise

        await drain_pending_agent_steps(timeout_s=_TASK_PROGRESS_DRAIN_TERMINAL_S)
        await emit_last_agent_step_snapshot()
        await asyncio.sleep(_TASK_PROGRESS_STEP_DRAIN_S)
        phase, note = _terminal_phase_from_result(result)
        await emit_task_progress(phase=phase, step=None, note=note)
        await asyncio.sleep(_TASK_PROGRESS_DRAIN_TERMINAL_S)
        return result


@mcp.tool(name="web_task_agent_github", task=TaskConfig(mode="required"))
async def web_task_agent_github(
    url: str,
    task: str,
    ctx: Context | None = None,
    headless_browser: bool = True,
    mode: str | None = None,
    budget_s: float | None = None,
    max_steps: int | None = None,
    step_timeout_s: float | None = None,
    progress: Progress = _PROGRESS_DEPENDENCY,
) -> list[TextContent]:
    max_steps_value = int(max_steps) if max_steps is not None and int(max_steps) > 0 else None
    with (
        task_progress_scope(progress=progress, max_steps=max_steps_value),
        propagate_cancelled_error(),
    ):
        await asyncio.sleep(_TASK_PROGRESS_INIT_DELAY_S)
        await emit_task_progress(phase="init", step=None, note="starting")
        try:
            result = await _call_with_identity(
                sdk_server.web_task_agent_github,
                url=url,
                task=task,
                ctx=ctx,  # type: ignore[arg-type]
                headless_browser=headless_browser,
                mode=mode,
                budget_s=budget_s,
                max_steps=max_steps,
                step_timeout_s=step_timeout_s,
            )
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None:
                current.uncancel()
            await cancel_pending_agent_steps(timeout_s=_TASK_PROGRESS_DRAIN_TERMINAL_S)
            await emit_task_progress(phase="cancelled", step=None, note="cancelled")
            raise
        except Exception as exc:  # noqa: BLE001
            await drain_pending_agent_steps(timeout_s=_TASK_PROGRESS_DRAIN_TERMINAL_S)
            await emit_task_progress(phase="failed", step=None, note=str(exc))
            await asyncio.sleep(_TASK_PROGRESS_DRAIN_TERMINAL_S)
            raise

        await drain_pending_agent_steps(timeout_s=_TASK_PROGRESS_DRAIN_TERMINAL_S)
        await emit_last_agent_step_snapshot()
        await asyncio.sleep(_TASK_PROGRESS_STEP_DRAIN_S)
        phase, note = _terminal_phase_from_result(result)
        await emit_task_progress(phase=phase, step=None, note=note)
        await asyncio.sleep(_TASK_PROGRESS_DRAIN_TERMINAL_S)
        return result


@mcp.tool(name="web_structured_flow")
async def web_structured_flow(
    record: dict[str, Any] | None = None,
    replay: dict[str, Any] | None = None,
    ctx: Context | None = None,
) -> list[TextContent]:
    with _docket_scope(ctx):
        result = await _call_with_identity(
            sdk_server.web_structured_flow,
            record=record,
            replay=replay,
            ctx=ctx,  # type: ignore[arg-type]
        )
    return result


@mcp.tool(name="web_eval_agent_submit")
async def web_eval_agent_submit(
    url: str,
    task: str,
    ctx: Context | None = None,
    headless_browser: bool = True,
    mode: str | None = None,
    budget_s: float | None = None,
    max_steps: int | None = None,
    step_timeout_s: float | None = None,
) -> list[TextContent]:
    from .optionb.compat_jobs import submit_job

    with _docket_scope(ctx):
        payload = await _call_with_identity(
            submit_job,
            tool_name="web_eval_agent",
            arguments={
                "url": url,
                "task": task,
                "headless_browser": headless_browser,
                "mode": mode,
                "budget_s": budget_s,
                "max_steps": max_steps,
                "step_timeout_s": step_timeout_s,
            },
        )
    return _json_text(payload.model_dump(mode="json"))


@mcp.tool(name="web_task_agent_submit")
async def web_task_agent_submit(
    url: str,
    task: str,
    ctx: Context | None = None,
    headless_browser: bool = True,
    mode: str | None = None,
    budget_s: float | None = None,
    max_steps: int | None = None,
    step_timeout_s: float | None = None,
) -> list[TextContent]:
    from .optionb.compat_jobs import submit_job

    with _docket_scope(ctx):
        payload = await _call_with_identity(
            submit_job,
            tool_name="web_task_agent",
            arguments={
                "url": url,
                "task": task,
                "headless_browser": headless_browser,
                "mode": mode,
                "budget_s": budget_s,
                "max_steps": max_steps,
                "step_timeout_s": step_timeout_s,
            },
        )
    return _json_text(payload.model_dump(mode="json"))


@mcp.tool(name="web_task_agent_github_submit")
async def web_task_agent_github_submit(
    url: str,
    task: str,
    ctx: Context | None = None,
    headless_browser: bool = True,
    mode: str | None = None,
    budget_s: float | None = None,
    max_steps: int | None = None,
    step_timeout_s: float | None = None,
) -> list[TextContent]:
    from .optionb.compat_jobs import submit_job

    with _docket_scope(ctx):
        payload = await _call_with_identity(
            submit_job,
            tool_name="web_task_agent_github",
            arguments={
                "url": url,
                "task": task,
                "headless_browser": headless_browser,
                "mode": mode,
                "budget_s": budget_s,
                "max_steps": max_steps,
                "step_timeout_s": step_timeout_s,
            },
        )
    return _json_text(payload.model_dump(mode="json"))


@mcp.tool(name="job_get")
async def job_get(
    job_id: str,
    ctx: Context | None = None,
) -> list[TextContent]:
    from .optionb.compat_jobs import job_get as compat_job_get

    with _docket_scope(ctx):
        payload = await _call_with_identity(compat_job_get, job_id=job_id)
    return _json_text(payload.model_dump(mode="json"))


@mcp.tool(name="job_result")
async def job_result(
    job_id: str,
    ctx: Context | None = None,
) -> list[TextContent]:
    from .optionb.compat_jobs import job_result as compat_job_result

    with _docket_scope(ctx):
        payload = await _call_with_identity(compat_job_result, job_id=job_id)
    if hasattr(payload, "model_dump"):
        return _json_text(payload.model_dump(mode="json"))
    return _json_text(payload)


@mcp.tool(name="job_wait")
async def job_wait(
    job_id: str,
    max_wait_s: int = 300,
    poll_interval_s: float = 2.0,
    ctx: Context | None = None,
) -> list[TextContent]:
    from .optionb.compat_jobs import job_wait as compat_job_wait

    with _docket_scope(ctx):
        payload = await _call_with_identity(
            compat_job_wait,
            job_id=job_id,
            max_wait_s=max_wait_s,
            poll_interval_s=poll_interval_s,
        )
    if hasattr(payload, "model_dump"):
        return _json_text(payload.model_dump(mode="json"))
    return _json_text(payload)


@mcp.tool(name="job_result_compact")
async def job_result_compact(
    job_id: str,
    ctx: Context | None = None,
) -> list[TextContent]:
    """Return a compact (log-friendly) job result payload."""

    from .optionb.compat_jobs import compact_payload_for_transport
    from .optionb.compat_jobs import job_result as compat_job_result

    with _docket_scope(ctx):
        payload = await _call_with_identity(compat_job_result, job_id=job_id)
    return _json_text(compact_payload_for_transport(payload))


@mcp.tool(name="job_wait_compact")
async def job_wait_compact(
    job_id: str,
    max_wait_s: int = 300,
    poll_interval_s: float = 2.0,
    ctx: Context | None = None,
) -> list[TextContent]:
    """Wait for a job and return a compact (log-friendly) payload.

    This avoids returning large artifacts (screenshots/DOM dumps) that can exceed
    orchestrator HTTP response limits.
    """

    from .optionb.compat_jobs import compact_payload_for_transport
    from .optionb.compat_jobs import job_wait as compat_job_wait

    with _docket_scope(ctx):
        payload = await _call_with_identity(
            compat_job_wait,
            job_id=job_id,
            max_wait_s=max_wait_s,
            poll_interval_s=poll_interval_s,
        )
    return _json_text(compact_payload_for_transport(payload))


@mcp.tool(name="job_cancel")
async def job_cancel(
    job_id: str,
    ctx: Context | None = None,
) -> list[TextContent]:
    from .optionb.compat_jobs import job_cancel as compat_job_cancel

    with _docket_scope(ctx):
        payload = await _call_with_identity(compat_job_cancel, job_id=job_id)
    return _json_text(payload.model_dump(mode="json"))


@mcp.tool(name="get_run_events")
async def get_run_events(
    session_id: str = "",
    last_n: int = 50,
    event_types: list[str] | None = None,
    from_timestamp: object | None = None,
    has_error: bool | None = None,
    include_details: bool = False,
    ctx: Context | None = None,
) -> list[TextContent]:
    identity = _resolve_identity_for_current_call()
    logger.info(
        "audit.artifact_list_query",
        extra={
            "artifact_kind": "run_events",
            "tenant_id": identity.tenant_id,
            "subject_id": identity.subject_id,
            "transport": identity.transport,
            "session_id": session_id,
            "last_n": int(last_n),
            "event_types": list(event_types) if event_types else None,
            "from_timestamp": from_timestamp,
            "has_error": has_error,
            "include_details": bool(include_details),
        },
    )
    with _docket_scope(ctx):
        return await _call_with_identity(
            sdk_server.get_run_events,
            session_id=session_id,
            last_n=last_n,
            event_types=event_types,
            from_timestamp=from_timestamp,
            has_error=has_error,
            include_details=include_details,
            ctx=ctx,  # type: ignore[arg-type]
        )


@mcp.tool(name="setup_browser_state")
async def setup_browser_state(
    url: str | None = None,
    state_id: str | None = None,
    ctx: Context | None = None,
) -> list[TextContent]:
    return await _call_with_identity(
        sdk_server.setup_browser_state,
        url=url,
        state_id=state_id,
        ctx=ctx,  # type: ignore[arg-type]
    )


@mcp.tool(name="get_screenshots")
async def get_screenshots(
    last_n: int = 5,
    screenshot_type: str = "agent_step",
    session_id: str = "",
    from_timestamp: float | None = None,
    has_error: bool | None = None,
    include_images: bool = True,
    ctx: Context | None = None,
) -> list[TextContent | ImageContent]:
    identity = _resolve_identity_for_current_call()
    logger.info(
        "audit.artifact_list_query",
        extra={
            "artifact_kind": "screenshots",
            "tenant_id": identity.tenant_id,
            "subject_id": identity.subject_id,
            "transport": identity.transport,
            "session_id": session_id,
            "last_n": int(last_n),
            "screenshot_type": str(screenshot_type),
            "from_timestamp": from_timestamp,
            "has_error": has_error,
            "include_images": bool(include_images),
        },
    )
    with _docket_scope(ctx):
        return await _call_with_identity(
            sdk_server.get_screenshots,
            last_n=last_n,
            screenshot_type=screenshot_type,
            session_id=session_id,
            from_timestamp=from_timestamp,
            has_error=has_error,
            include_images=include_images,
            ctx=ctx,  # type: ignore[arg-type]
        )


@mcp.tool(name="tasks_list")
async def tasks_list(
    limit: int | None = None,
    cursor: str | None = None,
    status: str | None = None,
    tool_name: str | None = None,
    since: str | None = None,
    ctx: Context | None = None,
) -> list[TextContent]:
    from pydantic import ValidationError

    from .optionb.ops_tasks import OpsTasksListQuery, OpsTasksServiceError, get_ops_tasks_service

    try:
        _require_http_scopes(required=("gsd:browser:read", "gsd:admin"))
        query = OpsTasksListQuery(
            limit=limit,
            cursor=cursor,
            status=status,  # type: ignore[arg-type]
            tool_name=tool_name,
            since=since,
        )
    except PermissionError:
        payload = {
            "version": "gsd.tasks_list.v1",
            "tasks": [],
            "next_cursor": None,
            "error": {
                "code": "forbidden",
                "message": "Insufficient scope",
                "details": {"required_scopes": ["gsd:browser:read", "gsd:admin"]},
            },
        }
        return _json_text(payload)
    except ValidationError as exc:
        payload = {
            "version": "gsd.tasks_list.v1",
            "tasks": [],
            "next_cursor": None,
            "error": {
                "code": "invalid_query",
                "message": "Invalid query",
                "details": {"errors": exc.errors()},
            },
        }
        return _json_text(payload)

    identity = _resolve_identity_for_current_call()
    try:
        with _docket_scope(ctx):
            service = get_ops_tasks_service()
            response = await service.list_tasks(identity=identity, query=query)
        body = response.model_dump(mode="json")
        payload = {
            "version": "gsd.tasks_list.v1",
            "tasks": body.get("tasks", []),
            "next_cursor": body.get("next_cursor"),
            "error": None,
        }
        return _json_text(payload)
    except OpsTasksServiceError as exc:
        payload = {
            "version": "gsd.tasks_list.v1",
            "tasks": [],
            "next_cursor": None,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details or None,
            },
        }
        return _json_text(payload)


@mcp.tool(name="tasks_admin_list")
async def tasks_admin_list(
    limit: int | None = None,
    cursor: str | None = None,
    status: str | None = None,
    tool_name: str | None = None,
    since: str | None = None,
    tenant_id: str | None = None,
    subject_id: str | None = None,
    transport: str | None = None,
    ctx: Context | None = None,
) -> list[TextContent]:
    from pydantic import ValidationError

    from .optionb.ops_tasks import (
        OpsAdminTasksListQuery,
        OpsTasksServiceError,
        get_ops_tasks_service,
    )

    if not _admin_mode_enabled():
        payload = {
            "version": "gsd.tasks_admin_list.v1",
            "tasks": [],
            "next_cursor": None,
            "error": {
                "code": "admin_disabled",
                "message": "Admin endpoints are disabled",
                "details": None,
            },
        }
        return _json_text(payload)

    try:
        _require_http_scopes(required=("gsd:admin",))
        query = OpsAdminTasksListQuery(
            limit=limit,
            cursor=cursor,
            status=status,  # type: ignore[arg-type]
            tool_name=tool_name,
            since=since,
            tenant_id=tenant_id,
            subject_id=subject_id,
            transport=transport,  # type: ignore[arg-type]
        )
    except PermissionError:
        payload = {
            "version": "gsd.tasks_admin_list.v1",
            "tasks": [],
            "next_cursor": None,
            "error": {
                "code": "forbidden",
                "message": "Insufficient scope",
                "details": {"required_scopes": ["gsd:admin"]},
            },
        }
        return _json_text(payload)
    except ValidationError as exc:
        payload = {
            "version": "gsd.tasks_admin_list.v1",
            "tasks": [],
            "next_cursor": None,
            "error": {
                "code": "invalid_query",
                "message": "Invalid query",
                "details": {"errors": exc.errors()},
            },
        }
        return _json_text(payload)

    try:
        with _docket_scope(ctx):
            service = get_ops_tasks_service()
            response = await service.admin_list_tasks(query=query)
        body = response.model_dump(mode="json")
        payload = {
            "version": "gsd.tasks_admin_list.v1",
            "tasks": body.get("tasks", []),
            "next_cursor": body.get("next_cursor"),
            "error": None,
        }
        return _json_text(payload)
    except OpsTasksServiceError as exc:
        payload = {
            "version": "gsd.tasks_admin_list.v1",
            "tasks": [],
            "next_cursor": None,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details or None,
            },
        }
        return _json_text(payload)


def run_stdio() -> None:
    from .optionb.task_backend import require_docket_redis_url

    _ = require_docket_redis_url()
    mcp.run(transport="stdio")
