"""FastMCP stdio server exposing browser integration tools."""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import logging
import os
import re
import time
import traceback
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ImageContent, TextContent

from .browser_state import browser_state_path_for_id, capture_state_interactive
from .config import Settings, load_settings
from .failure_ranking import rank_failures_for_session
from .llm.browser_use import create_browser_use_llms
from .run_event_capture import CDPRunEventCapture
from .run_event_store import RunEventStore
from .runtime import DEFAULT_DASHBOARD_HOST, DEFAULT_DASHBOARD_PORT, get_runtime
from .streaming.cdp_input_dispatch import (
    CDPInputDispatcher,
    CtrlTargetUnavailableError,
    dispatch_ctrl_input_event,
)
from .streaming.security import get_security_logger

logger = logging.getLogger("gsd_browser.mcp")

mcp = FastMCP("gsd")

os.environ.setdefault("BROWSER_USE_SETUP_LOGGING", "false")

_WEB_EVAL_AGENT_MODES = {"compact", "dev"}
_RUN_EVENT_TYPES = {"agent", "console", "network"}

_UNSET: object = object()
# Task-local overrides used by higher-level MCP tools that wrap `web_eval_agent`.
_BROWSER_STATE_ID_OVERRIDE: ContextVar[object] = ContextVar(
    "gsd_browser_state_id_override", default=_UNSET
)
_PROMPT_PROFILE_OVERRIDE: ContextVar[str] = ContextVar(
    "gsd_browser_prompt_profile_override", default="web_eval"
)
_SESSION_ID_OVERRIDE: ContextVar[object] = ContextVar(
    "gsd_browser_session_id_override", default=_UNSET
)


@contextmanager
def session_id_scope(session_id: str | None) -> object:
    """Optionally override the web_eval_agent session_id for this task."""
    if not session_id:
        yield
        return
    token = _SESSION_ID_OVERRIDE.set(str(session_id))
    try:
        yield
    finally:
        _SESSION_ID_OVERRIDE.reset(token)


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


def _normalize_url(url: str) -> str:
    if url.startswith(("http://", "https://", "file://", "data:", "chrome:", "javascript:")):
        return url
    return f"https://{url}"


def _browser_state_path() -> Path:
    return browser_state_path_for_id(None)


def _browser_state_path_for_id(state_id: str | None) -> Path:
    return browser_state_path_for_id(state_id)


def _truncate(text: str, *, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 1)] + "…"


def _public_url(url: str | None) -> str | None:
    if not url:
        return None
    raw = str(url).strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        cleaned = f"{parsed.scheme}://{parsed.netloc}{parsed.path or ''}"
        return _truncate(cleaned, max_len=1000) or None
    return _truncate(raw, max_len=1000) or None


def _parse_timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    try:
        return float(text)
    except ValueError:
        pass

    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.timestamp()
    except ValueError:
        return None


class TenantSessionLimitError(Exception):
    """Raised when a tenant exceeds their concurrent session limit."""

    def __init__(self, tenant_id: str, limit: int, active: int) -> None:
        self.tenant_id = tenant_id
        self.limit = limit
        self.active = active
        super().__init__(
            f"Tenant {tenant_id} has {active} active sessions"
            f" (limit: {limit})"
        )


def _get_caller_identity() -> tuple[str, str]:
    """Return (tenant_id, subject_id) for the current caller."""
    try:
        from .optionb.identity import STDIO_IDENTITY
        from .optionb.request_context import get_current_identity

        identity = get_current_identity() or STDIO_IDENTITY
        return identity.tenant_id, identity.subject_id
    except Exception:  # noqa: BLE001
        return "local", "local"


def _register_session_in_registry(
    *,
    registry: Any,
    session_id: str,
    settings: Settings,
) -> None:
    """Register a new session in the SessionRegistry if available.

    Raises TenantSessionLimitError if the tenant's active session count
    would exceed GSD_MAX_SESSIONS_PER_TENANT.
    """
    if registry is None:
        return
    create = getattr(registry, "create_session", None)
    if not callable(create):
        return
    tenant_id, subject_id = _get_caller_identity()
    worker_id = getattr(settings, "worker_id", "") or ""

    # Enforce tenant session limit (ADR-0026 / MS-7)
    max_sessions = getattr(settings, "max_sessions_per_tenant", 5)
    count_active = getattr(registry, "count_active_sessions", None)
    if callable(count_active):
        active = count_active(tenant_id)
        if active >= max_sessions:
            raise TenantSessionLimitError(
                tenant_id=tenant_id,
                limit=max_sessions,
                active=active,
            )

    try:
        stream_url = _build_stream_url(settings, session_id)
        create(
            session_id=session_id,
            owner_tenant_id=tenant_id,
            owner_subject_id=subject_id,
            worker_id=worker_id,
            stream_url=stream_url,
        )
    except Exception:  # noqa: BLE001
        logger.debug(
            "Failed to register session in registry",
            exc_info=True,
        )


def _terminate_session_in_registry(registry: Any, session_id: str) -> None:
    """Terminate a session in the SessionRegistry if available."""
    if registry is None:
        return
    terminate = getattr(registry, "terminate_session", None)
    if not callable(terminate):
        return
    try:
        terminate(session_id)
    except Exception:  # noqa: BLE001
        logger.debug("Failed to terminate session in registry", exc_info=True)


def _activate_session_in_registry(registry: Any, session_id: str) -> None:
    """Activate a session in the SessionRegistry if available."""
    if registry is None:
        return
    activate = getattr(registry, "activate_session", None)
    if not callable(activate):
        return
    try:
        activate(session_id)
    except Exception:  # noqa: BLE001
        logger.debug("Failed to activate session in registry", exc_info=True)


def _build_stream_url(settings: Settings, session_id: str) -> str | None:
    """Build the streaming URL for a session (ADR-0024 / RS-3).

    Uses public host/scheme if configured, otherwise falls back to
    localhost dashboard URL. Returns None if no dashboard is available.
    """
    public_host = getattr(settings, "streaming_public_host", "") or ""
    raw_scheme = getattr(settings, "streaming_public_scheme", "") or "wss"
    scheme = str(raw_scheme).strip().lower() or "wss"
    if scheme == "wss":
        scheme = "https"
    elif scheme == "ws":
        scheme = "http"
    if public_host:
        return f"{scheme}://{public_host}"

    bind_host = (
        getattr(settings, "streaming_bind_host", "")
        or DEFAULT_DASHBOARD_HOST
    )
    _ = session_id
    return f"http://{bind_host}:{DEFAULT_DASHBOARD_PORT}"


def _select_web_eval_agent_mode(*, normalized_url: str, explicit: str | None) -> str:
    if explicit is not None:
        candidate = str(explicit).strip().lower()
        if candidate not in _WEB_EVAL_AGENT_MODES:
            raise ValueError(
                f"Invalid mode={explicit!r}. Expected one of {sorted(_WEB_EVAL_AGENT_MODES)}."
            )
        return candidate

    hostname = urlparse(normalized_url).hostname
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return "dev"
    return "compact"


def _dev_run_event_excerpts(
    run_events: RunEventStore | None,
    *,
    session_id: str,
    base_url: str | None = None,
    history: Any | None = None,
    max_per_type: int = 5,
) -> dict[str, Any]:
    max_value = min(max(int(max_per_type), 0), 10)
    if run_events is None or max_value <= 0:
        return {"console_errors": [], "network_errors": [], "errors_top": []}

    get_events = getattr(run_events, "get_events", None)
    if not callable(get_events):
        return {"console_errors": [], "network_errors": [], "errors_top": []}

    events: list[dict[str, Any]] = get_events(
        session_id=session_id,
        last_n=100,
        event_types=["console", "network"],
        from_timestamp=None,
        has_error=True,
        include_details=True,
    )

    console_errors: list[dict[str, Any]] = []
    network_errors: list[dict[str, Any]] = []
    for event in events:
        event_type = event.get("event_type") or event.get("type")
        if event_type == "console" and len(console_errors) < max_value:
            console_errors.append(event)
        elif event_type == "network" and len(network_errors) < max_value:
            network_errors.append(event)
        if len(console_errors) >= max_value and len(network_errors) >= max_value:
            break

    errors_top = rank_failures_for_session(
        run_events=run_events,
        session_id=session_id,
        base_url=base_url,
        history=history,
        max_items=10,
    )

    return {
        "console_errors": console_errors,
        "network_errors": network_errors,
        "errors_top": errors_top,
    }


def _load_browser_use_classes() -> tuple[type[Any], type[Any]]:
    from browser_use import Agent, BrowserSession

    return Agent, BrowserSession


def _history_final_result(history: Any) -> str | None:
    final_result = getattr(history, "final_result", None)
    if callable(final_result):
        return final_result()
    return None


def _history_has_errors(history: Any) -> bool:
    has_errors = getattr(history, "has_errors", None)
    if callable(has_errors):
        return bool(has_errors())
    if isinstance(has_errors, bool):
        return has_errors
    return False


def _history_error_count(history: Any) -> int:
    errors_attr = getattr(history, "errors", None)
    if callable(errors_attr):
        errors_iter = errors_attr()
    else:
        errors_iter = errors_attr

    if errors_iter is None:
        return 0

    try:
        return sum(1 for err in errors_iter if err)
    except TypeError:
        return int(bool(errors_iter))


def _history_step_count(history: Any) -> int:
    steps = getattr(history, "history", None)
    if steps is None:
        return 0
    try:
        return len(steps)
    except TypeError:
        return 0


def _normalize_history_result(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        result = value.strip()
    else:
        result = str(value).strip()
    return result or None


def _extract_wrapped_result(value: str | None) -> tuple[str | None, str | None, str | None]:
    """Extract the prompt wrapper JSON payload if present.

    Returns (result, status, notes) where result falls back to the original string when parsing
    fails or the payload is missing expected keys.
    """
    if value is None:
        return None, None, None
    stripped = value.strip()
    if not stripped.startswith("{"):
        return value, None, None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return value, None, None
    if not isinstance(parsed, dict):
        return value, None, None

    extracted_result = _normalize_history_result(parsed.get("result"))
    extracted_status = _normalize_history_result(parsed.get("status"))
    extracted_notes = _normalize_history_result(parsed.get("notes"))
    return extracted_result or value, extracted_status, extracted_notes


def _record_history_errors_as_events(
    *,
    history: Any,
    run_events: Any,
    session_id: str,
    last_page_url: str | None,
    last_page_title: str | None,
) -> None:
    """Record validation and agent errors from history as agent events with has_error=True."""
    if run_events is None:
        return

    record_agent_event_fn = getattr(run_events, "record_agent_event", None)
    if not callable(record_agent_event_fn):
        return

    errors_attr = getattr(history, "errors", None)
    if callable(errors_attr):
        errors_iter = errors_attr()
    else:
        errors_iter = errors_attr

    if errors_iter is None:
        return

    try:
        iterator = iter(errors_iter)
    except TypeError:
        iterator = iter([errors_iter])

    for error in iterator:
        if not error:
            continue

        error_text = str(error).strip()
        if not error_text:
            continue

        # Check if this is a validation error or provider error
        error_lower = error_text.lower()
        is_validation_error = any(
            keyword in error_lower
            for keyword in ["validation", "pydantic", "schema", "field required", "invalid"]
        )
        is_provider_error = any(
            keyword in error_lower
            for keyword in ["provider", "api", "rate limit", "authentication", "model"]
        )

        if is_validation_error or is_provider_error:
            try:
                failure_type = "schema_validation" if is_validation_error else "provider_error"
                error_summary = _truncate(f"{failure_type}: {error_text}", max_len=1000)
                record_agent_event_fn(
                    session_id,
                    captured_at=datetime.now(UTC).timestamp(),
                    step=None,
                    url=last_page_url,
                    title=last_page_title,
                    summary=error_summary,
                    has_error=True,
                )
            except Exception:  # noqa: BLE001
                logger.debug("Failed to record history error as agent event", exc_info=True)


def _history_error_messages(history: Any, *, max_items: int = 8) -> list[str]:
    errors_attr = getattr(history, "errors", None)
    if callable(errors_attr):
        errors_iter = errors_attr()
    else:
        errors_iter = errors_attr

    if errors_iter is None:
        return []

    messages: list[str] = []
    try:
        iterator = iter(errors_iter)
    except TypeError:
        iterator = iter([errors_iter])

    for err in iterator:
        if not err:
            continue
        text = str(err).strip()
        if not text:
            continue
        text = _truncate(text, max_len=400)
        if text not in messages:
            messages.append(text)
        if len(messages) >= max_items:
            break
    return messages


def _dedupe(items: list[str]) -> list[str]:
    unique: list[str] = []
    for item in items:
        if item and item not in unique:
            unique.append(item)
    return unique


def _decode_base64_image(data: str) -> bytes | None:
    if not data:
        return None
    payload = data.strip()
    if payload.startswith("data:") and "," in payload:
        payload = payload.split(",", 1)[1].strip()
    try:
        return base64.b64decode(payload)
    except Exception:  # noqa: BLE001
        return None


def _browser_use_prompt_wrapper(*, base_url: str) -> str:
    return (
        "You are an automated browser agent running inside an MCP tool call.\n"
        f"Base URL: {base_url}\n\n"
        "Rules:\n"
        "- Start at the Base URL and stay on the same site unless the task explicitly "
        "requires leaving.\n"
        "- If the site requires login and you cannot proceed without credentials, STOP.\n"
        "- If you encounter a CAPTCHA, bot wall, or similar automated-access restriction, "
        "STOP.\n"
        "- If the task is impossible due to site restrictions (permissions, paywall, blocked "
        "flows), STOP.\n"
        "- You may retry a transient UI failure 1–2 times (timeouts, missed clicks), but do not "
        "loop.\n\n"
        "Output contract (browser-use):\n"
        "- You MUST respond with valid JSON containing an 'action' field that is a list (array).\n"
        "- The 'action' field must contain at least one action object.\n"
        "- CRITICAL: When using the done action, it must be wrapped in the action array "
        "like this:\n"
        '  {"action": [{"done": {"success": true, "text": "your message"}}]}\n'
        "- To stop for any reason (including completion), use the done action:\n"
        '  - {"action": [{"done": {"success": true, "text": "final answer"}}]} '
        "when completed successfully.\n"
        '  - {"action": [{"done": {"success": false, "text": "reason for stopping"}}]} '
        "for failures (login required, CAPTCHA/bot wall, impossible task).\n"
        "- NEVER output done at the top level - it must always be inside the action array.\n"
    )


def _browser_use_prompt_wrapper_web_task(*, base_url: str) -> str:
    return (
        "You are an automated browser agent running inside an MCP tool call.\n"
        f"Start URL: {base_url}\n\n"
        "Rules:\n"
        "- Start at the Start URL.\n"
        "- You may navigate away from the Start URL if (and only if) the task explicitly "
        "requires it.\n"
        "- Do not enter passwords, 2FA codes, or payment details.\n"
        "- Do not complete destructive actions (purchase, delete, cancel, submit irreversible "
        "forms) unless the task explicitly asks you to.\n"
        "- If the site requires login and you cannot proceed without credentials, STOP.\n"
        "- If you encounter a CAPTCHA, bot wall, or similar automated-access restriction, STOP.\n"
        "- If the task is impossible due to site restrictions (permissions, paywall, blocked "
        "flows), STOP.\n"
        "- You may retry a transient UI failure 1–2 times (timeouts, missed clicks), but do not "
        "loop.\n\n"
        "Output contract (browser-use):\n"
        "- You MUST respond with valid JSON containing an 'action' field that is a list (array).\n"
        "- The 'action' field must contain at least one action object.\n"
        "- CRITICAL: When using the done action, it must be wrapped in the action array "
        "like this:\n"
        '  {"action": [{"done": {"success": true, "text": "your message"}}]}\n'
        "- To stop for any reason (including completion), use the done action:\n"
        '  - {"action": [{"done": {"success": true, "text": "final answer"}}]} '
        "when completed successfully.\n"
        '  - {"action": [{"done": {"success": false, "text": "reason for stopping"}}]} '
        "for failures (login required, CAPTCHA/bot wall, impossible task).\n"
        "- NEVER output done at the top level - it must always be inside the action array.\n"
    )


def _browser_use_prompt_wrapper_for_profile(*, profile: str, base_url: str) -> str:
    normalized = str(profile).strip().lower() or "web_eval"
    if normalized == "web_task":
        return _browser_use_prompt_wrapper_web_task(base_url=base_url)
    return _browser_use_prompt_wrapper(base_url=base_url)


def _get_enhanced_system_prompt(*, base_url: str, tool_rules: str | None = None) -> str | None:
    """Load enhanced system prompt from file if override mode is enabled.

    Returns enhanced prompt string if GSD_OVERRIDE_SYSTEM_PROMPT=1,
    otherwise returns None.

    Modes:
    - LITE (default): Double reinforcement (early + end), minimal size increase
    - FULL: Triple reinforcement (early, middle, end), +47% size increase

    The enhanced prompt is based on browser-use v0.11.2 system_prompt.md with:
    - LITE: Short JSON reminder after intro + original output section
    - FULL: Triple reinforcement with 6 examples and visual markers

    See: artifacts/real_world_sanity/SYSTEM_PROMPT_OVERRIDE_PROPOSAL.md
    """
    if os.getenv("GSD_OVERRIDE_SYSTEM_PROMPT") != "1":
        return None

    try:
        # Check if FULL mode is requested, otherwise use LITE
        use_full = os.getenv("GSD_OVERRIDE_FULL") == "1"
        filename = "system_prompt_enhanced.md" if use_full else "system_prompt_enhanced_lite.md"
        prompt_path = Path(__file__).parent / "custom_prompts" / filename

        if not prompt_path.exists():
            logger.warning(
                "enhanced_prompt_not_found",
                extra={"path": str(prompt_path), "override_mode": "enabled", "use_full": use_full},
            )
            return None

        enhanced_prompt = prompt_path.read_text(encoding="utf-8")

        # Append our MCP-specific rules to the enhanced prompt
        mcp_rules = (
            "\n\n"
            "MCP Tool Context:\n"
            "You are an automated browser agent running inside an MCP tool call.\n"
            f"Base URL: {base_url}\n\n"
            "Rules:\n"
            "- Start at the Base URL and stay on the same site unless the task explicitly "
            "requires leaving.\n"
            "- If the site requires login and you cannot proceed without credentials, STOP.\n"
            "- If you encounter a CAPTCHA, bot wall, or similar automated-access restriction, "
            "STOP.\n"
            "- If the task is impossible due to site restrictions (permissions, paywall, blocked "
            "flows), STOP.\n"
            "- You may retry a transient UI failure 1–2 times (timeouts, missed clicks), "
            "but do not loop.\n"
            "- To stop for any reason (including completion), use the done action:\n"
            '  - {"action": [{"done": {"success": true, "text": "final answer"}}]} '
            "when completed successfully.\n"
            '  - {"action": [{"done": {"success": false, "text": "reason for stopping"}}]} '
            "for failures (login required, CAPTCHA/bot wall, impossible task).\n"
        )

        if tool_rules:
            mcp_rules = mcp_rules + "\n\nTool-specific guidance:\n" + tool_rules.strip() + "\n"

        return enhanced_prompt + mcp_rules
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "failed_to_load_enhanced_prompt",
            extra={"error": str(exc)},
            exc_info=True,
        )
        return None


def _agent_output_summary(agent_output: Any) -> str | None:
    actions = getattr(agent_output, "action", None)
    if actions is None and isinstance(agent_output, dict):
        actions = agent_output.get("action")
    if not isinstance(actions, list):
        return None

    action_names: list[str] = []
    for action in actions:
        payload: Any = action
        if hasattr(action, "model_dump") and callable(action.model_dump):
            try:
                payload = action.model_dump()
            except Exception:  # noqa: BLE001
                payload = action

        if isinstance(payload, dict):
            present = [key for key, value in payload.items() if value not in (None, {}, [], "")]
            if present:
                action_names.append(str(present[0]))
            continue

        action_names.append(type(payload).__name__)

    if not action_names:
        return None
    unique: list[str] = []
    for name in action_names:
        if name not in unique:
            unique.append(name)
    return _truncate("actions=" + ",".join(unique[:8]), max_len=1000)


@mcp.tool(name="web_eval_agent")
async def web_eval_agent(
    url: str,
    task: str,
    ctx: Context,
    headless_browser: bool = False,
    mode: str | None = None,
    budget_s: float | None = None,
    max_steps: int | None = None,
    step_timeout_s: float | None = None,
) -> list[TextContent]:
    """Evaluate the user experience / interface of a web application.

    This tool allows the AI to assess the quality of user experience and interface design
    of a web application by performing specific tasks and analyzing the interaction flow.

    Before this tool is used, the web application should already be running locally on a port.

    Args:
        url: Required. The localhost URL of the web application to evaluate, including the port
            number. Example: http://localhost:3000, http://localhost:8080,
            http://localhost:4200, http://localhost:5173, etc.
            Try to avoid using the path segments of the URL, and instead use the root URL.
        task: Required. The specific UX/UI aspect to test (e.g., "test the checkout flow",
             "evaluate the navigation menu usability", "check form validation feedback")
             Be as detailed as possible in your task description. It could be anywhere from 2
             sentences to 2 paragraphs.
        headless_browser: Optional. Whether to hide the browser window popup during evaluation.
        If headless_browser is True, only the operative control center browser will show, and no
        popup browser will be shown.
        mode: Optional. Response mode:
          - "compact": minimal summary + references (default for non-localhost)
          - "dev": includes bounded console/network excerpts (default for localhost/127.0.0.1)
        budget_s: Optional. Tool-level budget in seconds (overall wall-clock).
            IMPORTANT: Do not set this unless the user explicitly asks to override timeouts.
            Leave it unset to use the server defaults (`GSD_WEB_EVAL_BUDGET_S`).
        max_steps: Optional. Maximum number of browser-use steps.
            IMPORTANT: Do not set this unless the user explicitly asks to override limits.
            Leave it unset to use the server defaults (`GSD_WEB_EVAL_MAX_STEPS`).
        step_timeout_s: Optional. Per-step timeout in seconds.
            IMPORTANT: Do not set this unless the user explicitly asks to override timeouts.
            Leave it unset to use the server defaults (`GSD_WEB_EVAL_STEP_TIMEOUT_S`).

    Returns:
        list[TextContent]: A single JSON payload encoded as text (no inline images).
    """
    _ = ctx
    runtime = get_runtime()
    settings = load_settings(strict=False)
    ensure_dashboard_running = getattr(runtime, "ensure_dashboard_running", None)
    if callable(ensure_dashboard_running):
        bind_host = getattr(settings, "streaming_bind_host", "") or DEFAULT_DASHBOARD_HOST
        ensure_dashboard_running(
            settings=settings, host=bind_host, port=DEFAULT_DASHBOARD_PORT
        )

    dashboard_fn = getattr(runtime, "dashboard", None)
    dashboard = dashboard_fn() if callable(dashboard_fn) else None
    streaming_runtime = getattr(dashboard, "runtime", None) if dashboard else None
    control_state = getattr(streaming_runtime, "control_state", None) if streaming_runtime else None
    cdp_streamer = getattr(streaming_runtime, "cdp_streamer", None) if streaming_runtime else None
    streaming_stats = getattr(streaming_runtime, "stats", None) if streaming_runtime else None
    session_registry = getattr(streaming_runtime, "registry", None) if streaming_runtime else None

    tool_call_id = str(uuid.uuid4())
    override = _SESSION_ID_OVERRIDE.get()
    session_id = str(uuid.uuid4()) if override is _UNSET else str(override)
    started = datetime.now(UTC).timestamp()
    normalized_url = _normalize_url(url)

    # Register session in SessionRegistry (ADR-0026)
    try:
        _register_session_in_registry(
            registry=session_registry,
            session_id=session_id,
            settings=settings,
        )
    except TenantSessionLimitError as exc:
        payload = {
            "version": "gsd.web_eval_agent.v1",
            "session_id": session_id,
            "tool_call_id": tool_call_id,
            "url": normalized_url,
            "task": task,
            "mode": None,
            "requested_mode": str(mode) if mode is not None else None,
            "status": "failed",
            "result": None,
            "summary": str(exc),
            "page": {"url": None, "title": None},
            "errors_top": [],
            "timeouts": {
                "budget_s": None,
                "step_timeout_s": None,
                "max_steps": None,
                "timed_out": False,
            },
            "warnings": [],
            "artifacts": {
                "screenshots": 0,
                "stream_samples": 0,
                "run_events": 0,
            },
            "next_actions": [
                "Wait for existing sessions to complete.",
                (
                    "Increase GSD_MAX_SESSIONS_PER_TENANT"
                    f" (current: {exc.limit})."
                ),
            ],
        }
        return [
            TextContent(
                type="text",
                text=json.dumps(payload, ensure_ascii=False),
            )
        ]

    warnings: list[str] = []
    # Get defaults from settings (may be None if not set in env)
    default_budget_s = getattr(settings, "web_eval_budget_s", None)
    default_max_steps = getattr(settings, "web_eval_max_steps", None)
    default_step_timeout_s = getattr(settings, "web_eval_step_timeout_s", None)
    try:
        # Priority: MCP client params > env vars > None (browser-use defaults)
        effective_budget_s: float | None = (
            float(budget_s) if budget_s is not None
            else float(default_budget_s) if default_budget_s is not None
            else None
        )
        effective_max_steps: int | None = (
            int(max_steps) if max_steps is not None
            else int(default_max_steps) if default_max_steps is not None
            else None
        )
        effective_step_timeout_s: float | None = (
            float(step_timeout_s) if step_timeout_s is not None
            else float(default_step_timeout_s) if default_step_timeout_s is not None
            else None
        )
        # Validation: if set, values must be positive
        if effective_budget_s is not None and effective_budget_s <= 0:
            raise ValueError("budget_s must be > 0")
        if effective_max_steps is not None and effective_max_steps <= 0:
            raise ValueError("max_steps must be > 0")
        if effective_step_timeout_s is not None and effective_step_timeout_s <= 0:
            raise ValueError("step_timeout_s must be > 0")
    except (TypeError, ValueError) as exc:
        payload = {
            "version": "gsd.web_eval_agent.v1",
            "session_id": session_id,
            "tool_call_id": tool_call_id,
            "url": normalized_url,
            "task": task,
            "mode": None,
            "requested_mode": str(mode) if mode is not None else None,
            "status": "failed",
            "result": None,
            "summary": _truncate(str(exc), max_len=2000),
            "page": {"url": None, "title": None},
            "errors_top": [],
            "timeouts": {
                "budget_s": default_budget_s,
                "step_timeout_s": default_step_timeout_s,
                "max_steps": default_max_steps,
                "timed_out": False,
            },
            "warnings": [],
            "artifacts": {"screenshots": 0, "stream_samples": 0, "run_events": 0},
            "next_actions": [
                "Pass positive budget_s/max_steps/step_timeout_s values.",
                f"Open dashboard: http://{DEFAULT_DASHBOARD_HOST}:{DEFAULT_DASHBOARD_PORT}",
            ],
        }
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
    try:
        selected_mode = _select_web_eval_agent_mode(normalized_url=normalized_url, explicit=mode)
    except ValueError as exc:
        payload = {
            "version": "gsd.web_eval_agent.v1",
            "session_id": session_id,
            "tool_call_id": tool_call_id,
            "url": normalized_url,
            "task": task,
            "mode": None,
            "requested_mode": str(mode) if mode is not None else None,
            "status": "failed",
            "result": None,
            "summary": _truncate(str(exc), max_len=2000),
            "page": {"url": None, "title": None},
            "errors_top": [],
            "timeouts": {
                "budget_s": effective_budget_s,
                "step_timeout_s": effective_step_timeout_s,
                "max_steps": effective_max_steps,
                "timed_out": False,
            },
            "warnings": warnings,
            "artifacts": {"screenshots": 0, "stream_samples": 0, "run_events": 0},
            "next_actions": [
                "Use mode='compact' or mode='dev' to override response behavior.",
                f"Open dashboard: http://{DEFAULT_DASHBOARD_HOST}:{DEFAULT_DASHBOARD_PORT}",
            ],
        }
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
    run_events = getattr(runtime, "run_events", None)
    if run_events is None:
        run_events = RunEventStore()
    ensure_session = getattr(run_events, "ensure_session", None)
    if callable(ensure_session):
        ensure_session(session_id, created_at=started)

    if hasattr(runtime, "screenshots"):
        try:
            runtime.screenshots.current_session_id = session_id
            runtime.screenshots.current_session_start = started
        except Exception:  # noqa: BLE001
            pass

    logger.info(
        "web_eval_agent called",
        extra={
            "tool_call_id": tool_call_id,
            "session_id": session_id,
            "url": normalized_url,
            "headless": headless_browser,
        },
    )

    state_override = _BROWSER_STATE_ID_OVERRIDE.get()
    if state_override is _UNSET:
        state_path = _browser_state_path_for_id(None)
        storage_state: str | None = str(state_path) if state_path.exists() else None
    elif state_override is None:
        storage_state = None
    else:
        state_path = _browser_state_path_for_id(str(state_override))
        storage_state = str(state_path) if state_path.exists() else None
    step_screenshot_count = 0
    recorded_step_numbers: set[int] = set()
    last_step_observed: int | None = None
    last_page_url: str | None = None
    last_page_title: str | None = None
    last_browser_errors: list[Any] = []
    last_has_error = False
    streaming_disabled_reason: str | None = None

    def _count_stream_samples() -> int:
        screenshots = getattr(runtime, "screenshots", None)
        count = getattr(screenshots, "count_screenshots", None) if screenshots is not None else None
        if not callable(count):
            return 0
        try:
            return int(count(screenshot_type="stream_sample", session_id=session_id))
        except Exception:  # noqa: BLE001
            return 0

    try:
        Agent, BrowserSession = _load_browser_use_classes()
        cdp_capture = CDPRunEventCapture(store=run_events, session_id=session_id)
        history: Any | None = None
        browser_session: Any | None = None

        def _coerce_step(value: Any) -> int | None:
            if value is None or isinstance(value, bool):
                return None
            if isinstance(value, int):
                return value
            try:
                return int(str(value).strip())
            except (TypeError, ValueError):
                return None

        async def _capture_current_page_screenshot(
            session: Any,
        ) -> tuple[bytes | None, str | None, str | None]:
            get_current_page = getattr(session, "get_current_page", None)
            if not callable(get_current_page):
                return None, None, None

            try:
                page = get_current_page()
                if inspect.isawaitable(page):
                    page = await page
            except Exception:  # noqa: BLE001
                return None, None, None

            if page is None:
                return None, None, None

            image_bytes: bytes | None = None
            for options in (
                {"format": "jpeg", "quality": 80},
                {"type": "jpeg", "quality": 80},
                {},
            ):
                try:
                    screenshot = page.screenshot(**options)
                    image_bytes = (
                        await screenshot if inspect.isawaitable(screenshot) else screenshot
                    )
                    if image_bytes:
                        break
                except TypeError:
                    continue
                except Exception:  # noqa: BLE001
                    return None, None, None

            if not image_bytes:
                return None, None, None

            page_url: str | None = None
            try:
                url_value = getattr(page, "url", None)
                page_url = str(url_value() if callable(url_value) else url_value or "") or None
            except Exception:  # noqa: BLE001
                page_url = None

            page_title: str | None = None
            try:
                title_value = getattr(page, "title", None)
                if callable(title_value):
                    title_result = title_value()
                    page_title = (
                        str(await title_result)
                        if inspect.isawaitable(title_result)
                        else str(title_result)
                    ) or None
                else:
                    page_title = str(title_value or "") or None
            except Exception:  # noqa: BLE001
                page_title = None

            return image_bytes, page_url, page_title

        async def record_step_screenshot(*args: Any, **kwargs: Any) -> None:
            nonlocal step_screenshot_count
            nonlocal \
                last_step_observed, \
                last_page_url, \
                last_page_title, \
                last_browser_errors, \
                last_has_error

            browser_state_summary = args[0] if args else kwargs.get("browser_state_summary")
            step = kwargs.get("step")
            if step is None and len(args) >= 3:
                step = args[2]

            step_number = _coerce_step(step)
            if step_number is None and browser_state_summary is not None:
                step_number = _coerce_step(getattr(browser_state_summary, "step", None))
                if step_number is None and hasattr(browser_state_summary, "get"):
                    try:
                        step_number = _coerce_step(browser_state_summary.get("step"))
                    except Exception:  # noqa: BLE001
                        step_number = None
            if step_number is not None:
                last_step_observed = step_number

            screenshot_base64 = None
            if browser_state_summary is not None:
                screenshot_base64 = getattr(browser_state_summary, "screenshot", None)
                if screenshot_base64 is None:
                    screenshot_base64 = getattr(browser_state_summary, "screenshot_base64", None)
                if screenshot_base64 is None and hasattr(browser_state_summary, "get"):
                    try:
                        screenshot_base64 = browser_state_summary.get("screenshot")
                    except Exception:  # noqa: BLE001
                        screenshot_base64 = None
                if screenshot_base64 is None and hasattr(browser_state_summary, "get"):
                    try:
                        screenshot_base64 = browser_state_summary.get("screenshot_base64")
                    except Exception:  # noqa: BLE001
                        screenshot_base64 = None

            if screenshot_base64 is None:
                screenshot_base64 = kwargs.get("screenshot")

            page_url_value = getattr(browser_state_summary, "url", None)
            if page_url_value is None and hasattr(browser_state_summary, "get"):
                try:
                    page_url_value = browser_state_summary.get("url")
                except Exception:  # noqa: BLE001
                    page_url_value = None

            page_title_value = getattr(browser_state_summary, "title", None)
            if page_title_value is None and hasattr(browser_state_summary, "get"):
                try:
                    page_title_value = browser_state_summary.get("title")
                except Exception:  # noqa: BLE001
                    page_title_value = None

            browser_errors = getattr(browser_state_summary, "browser_errors", None)
            if browser_errors is None and hasattr(browser_state_summary, "get"):
                try:
                    browser_errors = browser_state_summary.get("browser_errors")
                except Exception:  # noqa: BLE001
                    browser_errors = None

            page_url = str(page_url_value or "") or None
            page_title = str(page_title_value or "") or None
            browser_error_list: list[Any]
            if isinstance(browser_errors, (list, tuple)):
                browser_error_list = list(browser_errors)
            elif browser_errors:
                browser_error_list = [browser_errors]
            else:
                browser_error_list = []
            has_error = bool(browser_error_list)
            if page_url:
                last_page_url = page_url
            if page_title:
                last_page_title = page_title
            last_browser_errors = browser_error_list
            last_has_error = has_error

            image_bytes = (
                _decode_base64_image(screenshot_base64)
                if isinstance(screenshot_base64, str)
                else None
            )
            source = "browser_state_summary"
            mime_type = "image/png"

            if not image_bytes:
                (
                    fallback_bytes,
                    fallback_url,
                    fallback_title,
                ) = await _capture_current_page_screenshot(browser_session)
                if not fallback_bytes:
                    return
                image_bytes = fallback_bytes
                source = "current_page_fallback"
                mime_type = "image/jpeg"
                if not page_url and fallback_url:
                    page_url = fallback_url
                    last_page_url = fallback_url
                if not page_title and fallback_title:
                    page_title = fallback_title
                    last_page_title = fallback_title

            screenshots_manager = getattr(runtime, "screenshots", None)
            record = getattr(screenshots_manager, "record_screenshot", None)
            if not callable(record):
                return
            shot = record(
                screenshot_type="agent_step",
                image_bytes=image_bytes,
                source=source,
                mime_type=mime_type,
                session_id=session_id,
                captured_at=datetime.now(UTC).timestamp(),
                has_error=has_error,
                metadata={
                    "title": str(page_title or ""),
                    "browser_errors": list(browser_error_list),
                    "source": source,
                },
                url=page_url,
                step=step_number,
            )
            try:
                from .optionb.screenshot_artifacts import persist_screenshot

                if shot is not None:
                    await persist_screenshot(shot)
            except Exception:  # noqa: BLE001
                pass
            step_screenshot_count += 1
            if step_number is not None:
                recorded_step_numbers.add(step_number)

        async def record_guarantee_step_screenshot(*, step: int, reason: str) -> None:
            nonlocal step_screenshot_count

            screenshots_manager = getattr(runtime, "screenshots", None)
            record = getattr(screenshots_manager, "record_screenshot", None)
            if not callable(record):
                return

            image_bytes, page_url, page_title = await _capture_current_page_screenshot(
                browser_session
            )
            if not image_bytes:
                return

            url = last_page_url or page_url
            title = last_page_title or page_title or ""
            shot = record(
                screenshot_type="agent_step",
                source="current_page_fallback",
                image_bytes=image_bytes,
                mime_type="image/jpeg",
                session_id=session_id,
                captured_at=datetime.now(UTC).timestamp(),
                has_error=last_has_error,
                metadata={
                    "title": str(title),
                    "browser_errors": list(last_browser_errors),
                    "source": "current_page_fallback",
                    "capture_reason": reason,
                },
                url=url,
                step=step,
            )
            try:
                from .optionb.screenshot_artifacts import persist_screenshot

                if shot is not None:
                    await persist_screenshot(shot)
            except Exception:  # noqa: BLE001
                pass
            step_screenshot_count += 1
            recorded_step_numbers.add(step)

        async def ensure_required_step_screenshots() -> None:
            if 1 not in recorded_step_numbers:
                await record_guarantee_step_screenshot(step=1, reason="guarantee_step_1")

            final_step: int | None = None
            if history is not None:
                final_step = _history_step_count(history)
            if final_step is None:
                final_step = last_step_observed

            if (
                final_step is not None
                and final_step > 0
                and final_step not in recorded_step_numbers
            ):
                await record_guarantee_step_screenshot(
                    step=final_step, reason="guarantee_final_step"
                )

        def record_step_event(*args: Any, **kwargs: Any) -> None:
            browser_state_summary = args[0] if args else kwargs.get("browser_state_summary")
            agent_output = args[1] if len(args) >= 2 else kwargs.get("agent_output")
            step = kwargs.get("step")
            if step is None and len(args) >= 3:
                step = args[2]

            summary = _agent_output_summary(agent_output)

            page_url = None
            page_title = None
            if browser_state_summary is not None:
                page_url = getattr(browser_state_summary, "url", None)
                if page_url is None and hasattr(browser_state_summary, "get"):
                    try:
                        page_url = browser_state_summary.get("url")
                    except Exception:  # noqa: BLE001
                        page_url = None

                page_title = getattr(browser_state_summary, "title", None)
                if page_title is None and hasattr(browser_state_summary, "get"):
                    try:
                        page_title = browser_state_summary.get("title")
                    except Exception:  # noqa: BLE001
                        page_title = None

            record_agent_event = getattr(run_events, "record_agent_event", None)
            if callable(record_agent_event):
                record_agent_event(
                    session_id,
                    captured_at=datetime.now(UTC).timestamp(),
                    step=int(step) if isinstance(step, int) else None,
                    url=str(page_url) if page_url else None,
                    title=str(page_title) if page_title else None,
                    summary=summary,
                )

        async def on_new_step(*args: Any, **kwargs: Any) -> None:
            try:
                await record_step_screenshot(*args, **kwargs)
            except Exception:  # noqa: BLE001
                logger.debug("Failed to record step screenshot", exc_info=True)
            try:
                record_step_event(*args, **kwargs)
            except Exception:  # noqa: BLE001
                logger.debug("Failed to record agent step event", exc_info=True)

        # Let browser-use handle model-specific timeouts (90s for Claude, 60s default)
        llms = create_browser_use_llms(settings, timeout_s=settings.llm_timeout_s)
        llm = llms.primary
        browser_executable_path = getattr(settings, "browser_executable_path", "") or None
        browser_session = BrowserSession(
            headless=headless_browser,
            storage_state=storage_state,
            executable_path=browser_executable_path,
        )

        streaming_attach_task: asyncio.Task[None] | None = None

        active_session_set = False
        cdp_dispatcher: CDPInputDispatcher | None = None
        security_logger = get_security_logger()
        if control_state is not None:
            set_active_session = getattr(control_state, "set_active_session", None)
            if callable(set_active_session):
                set_active_session(session_id=session_id)
                active_session_set = True
            get_or_create_cdp_session = getattr(browser_session, "get_or_create_cdp_session", None)

            # Activate session in registry now that browser is up (ADR-0026)
            _activate_session_in_registry(session_registry, session_id)

            async def _send_ctrl_input(event: str, payload: dict[str, Any]) -> None:
                if not callable(get_or_create_cdp_session):
                    raise CtrlTargetUnavailableError("target_unavailable")

                for attempt in range(2):
                    try:
                        cdp_session = get_or_create_cdp_session()
                        if inspect.isawaitable(cdp_session):
                            cdp_session = await cdp_session
                    except Exception as exc:  # noqa: BLE001
                        if attempt == 0:
                            await asyncio.sleep(0.05)
                            continue
                        raise CtrlTargetUnavailableError("target_unavailable") from exc

                    cdp_client = getattr(cdp_session, "cdp_client", None)
                    cdp_session_id = getattr(cdp_session, "session_id", None)
                    if (
                        cdp_client is None
                        or not isinstance(cdp_session_id, str)
                        or not cdp_session_id
                    ):
                        if attempt == 0:
                            await asyncio.sleep(0.05)
                            continue
                        raise CtrlTargetUnavailableError("target_unavailable")

                    try:
                        await dispatch_ctrl_input_event(
                            cdp_client=cdp_client,
                            cdp_session_id=cdp_session_id,
                            event=event,
                            payload=payload,
                        )
                        return
                    except Exception:  # noqa: BLE001
                        if attempt == 0:
                            await asyncio.sleep(0.05)
                            continue
                        raise

            cdp_dispatcher = CDPInputDispatcher(send=_send_ctrl_input)
            # Register direct dispatcher so Socket.IO handlers can dispatch
            # CDP input immediately (like web-agent) instead of only via queue.
            main_loop = asyncio.get_running_loop()
            set_input_dispatcher = getattr(control_state, "set_input_dispatcher", None)
            if callable(set_input_dispatcher):
                set_input_dispatcher(cdp_dispatcher.dispatch, main_loop)
                logger.info(
                    "Registered direct CDP input dispatcher on control_state (loop=%s)",
                    id(main_loop),
                )

        cdp_attached = False

        def _get_cdp_client_safe(session: Any) -> Any:
            """Safely get cdp_client, handling AssertionError from browser-use."""
            try:
                return session.cdp_client
            except (AttributeError, AssertionError):
                return None

        async def attach_streaming_when_ready() -> None:
            nonlocal streaming_disabled_reason
            if cdp_streamer is None:
                return
            if getattr(streaming_stats, "streaming_mode", None) != "cdp":
                return

            started_wait = time.time()
            while True:
                # browser-use's cdp_client property raises AssertionError before connection
                cdp_client = _get_cdp_client_safe(browser_session)
                if cdp_client is not None:
                    break
                if time.time() - started_wait > 10.0:
                    streaming_disabled_reason = "cdp_not_ready"
                    note_detached = getattr(streaming_stats, "note_cdp_detached", None)
                    if callable(note_detached):
                        note_detached(error=streaming_disabled_reason)
                    return
                await asyncio.sleep(0.05)

            # Wait for session_manager to be initialized (required for get_or_create_cdp_session)
            while True:
                session_manager = getattr(browser_session, "session_manager", None)
                if session_manager is not None:
                    break
                if time.time() - started_wait > 10.0:
                    streaming_disabled_reason = "session_manager_not_ready"
                    note_detached = getattr(streaming_stats, "note_cdp_detached", None)
                    if callable(note_detached):
                        note_detached(error=streaming_disabled_reason)
                    return
                await asyncio.sleep(0.05)

            # Wait for agent to have navigated (agent_focus_target_id must be set)
            while True:
                agent_focus_target_id = getattr(browser_session, "agent_focus_target_id", None)
                if agent_focus_target_id is not None:
                    break
                if time.time() - started_wait > 10.0:
                    streaming_disabled_reason = "agent_focus_not_ready"
                    note_detached = getattr(streaming_stats, "note_cdp_detached", None)
                    if callable(note_detached):
                        note_detached(error=streaming_disabled_reason)
                    return
                await asyncio.sleep(0.05)

            # Retry start_browser_use a few times - session manager may need time to initialize
            start_browser_use = getattr(cdp_streamer, "start_browser_use", None)
            if not callable(start_browser_use):
                streaming_disabled_reason = "cdp_streamer.start_browser_use unavailable"
                note_detached = getattr(streaming_stats, "note_cdp_detached", None)
                if callable(note_detached):
                    note_detached(error=streaming_disabled_reason)
                return

            last_error: Exception | None = None
            for _attempt in range(20):  # Up to ~2 seconds of retries
                try:
                    await start_browser_use(browser_session=browser_session, session_id=session_id)
                    return  # Success
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    # Check if we've exceeded overall timeout
                    if time.time() - started_wait > 10.0:
                        break
                    await asyncio.sleep(0.1)

            if last_error is not None:
                err_msg = f"{type(last_error).__name__}: {last_error}"
                streaming_disabled_reason = _truncate(err_msg, max_len=400)
                note_detached = getattr(streaming_stats, "note_cdp_detached", None)
                if callable(note_detached):
                    note_detached(error=streaming_disabled_reason)

        async def attach_cdp_when_ready() -> None:
            nonlocal cdp_attached
            while True:
                # browser-use's cdp_client property raises AssertionError before connection
                cdp_client = _get_cdp_client_safe(browser_session)
                if cdp_client is not None:
                    try:
                        cdp_capture.attach(cdp_client)
                        cdp_attached = True
                    except Exception:  # noqa: BLE001
                        logger.debug("Failed to attach CDP event capture", exc_info=True)
                    return
                await asyncio.sleep(0.05)

        cdp_attach_task = asyncio.create_task(attach_cdp_when_ready())
        streaming_attach_task = asyncio.create_task(attach_streaming_when_ready())

        async def stop_browser_session() -> None:
            stop = getattr(browser_session, "stop", None)
            close = getattr(browser_session, "close", None)
            target = stop if callable(stop) else close if callable(close) else None
            if target is None:
                return
            try:
                result = target()
                if inspect.isawaitable(result):
                    await result
            except Exception:  # noqa: BLE001
                logger.debug("Failed to stop browser_use session", exc_info=True)

        async def pause_gate(*_: Any, **__: Any) -> None:
            if control_state is None:
                return

            is_paused = getattr(control_state, "is_paused", None)

            def _paused() -> bool:
                if callable(is_paused):
                    return bool(is_paused())
                return bool(getattr(control_state, "paused", False))

            if not _paused():
                return

            wait_until_unpaused = getattr(control_state, "wait_until_unpaused", None)
            drain_input_events = getattr(control_state, "drain_input_events", None)

            if cdp_dispatcher is None or not callable(drain_input_events):
                if callable(wait_until_unpaused):
                    await wait_until_unpaused()
                return

            def _payload_meta(*, event: str, payload: dict[str, Any]) -> dict[str, Any]:
                meta: dict[str, Any] = {"payload_keys": sorted(payload.keys())}
                if event == "input_type":
                    text = payload.get("text")
                    if isinstance(text, str):
                        meta["text_len"] = len(text)
                return meta

            while _paused():
                drained = drain_input_events(max_items=100)
                for record in drained:
                    event = record.get("event")
                    payload = record.get("payload")
                    if not isinstance(event, str) or not isinstance(payload, dict):
                        continue
                    record_sid = record.get("sid")
                    record_seq = record.get("seq")
                    meta = _payload_meta(event=event, payload=payload)
                    try:
                        await cdp_dispatcher.dispatch(event, payload)
                    except CtrlTargetUnavailableError:
                        security_logger.info(
                            "ctrl_target_unavailable",
                            extra={
                                "session_id": session_id,
                                "sid": record_sid,
                                "seq": record_seq,
                                "event": event,
                                "reason": "target_unavailable",
                                **meta,
                            },
                        )
                    except Exception as exc:  # noqa: BLE001
                        security_logger.info(
                            "ctrl_dispatch_error",
                            extra={
                                "session_id": session_id,
                                "sid": record_sid,
                                "seq": record_seq,
                                "event": event,
                                "reason": "dispatch_error",
                                "error": _truncate(f"{type(exc).__name__}: {exc}", max_len=300),
                                **meta,
                            },
                        )

                if not drained:
                    await asyncio.sleep(0.05)

            leftover = drain_input_events()
            if leftover:
                logger.info(
                    "ctrl_input_dropped",
                    extra={
                        "session_id": session_id,
                        "dropped": len(leftover),
                        "reason": "resumed",
                    },
                )

        history: Any | None = None
        try:
            # Check if override mode is enabled
            prompt_profile = _PROMPT_PROFILE_OVERRIDE.get()
            prompt_wrapper = _browser_use_prompt_wrapper_for_profile(
                profile=prompt_profile, base_url=normalized_url
            )

            enhanced_prompt = _get_enhanced_system_prompt(
                base_url=normalized_url,
                tool_rules=None if prompt_profile == "web_eval" else prompt_wrapper,
            )
            use_override_mode = enhanced_prompt is not None

            if use_override_mode:
                logger.info(
                    "using_enhanced_system_prompt",
                    extra={"session_id": session_id, "prompt_length": len(enhanced_prompt)},
                )

            # Prepare agent configuration

            # Convert use_vision from string to proper type
            use_vision_raw = str(getattr(settings, "use_vision", "auto")).lower()
            use_vision: bool | str
            if use_vision_raw == "true":
                use_vision = True
            elif use_vision_raw == "false":
                use_vision = False
            else:
                use_vision = "auto"

            agent_kwargs: dict[str, Any] = {
                "task": task,
                "llm": llm,
                "browser_session": browser_session,
                "fallback_llm": llms.fallback,
                "initial_actions": [{"navigate": {"url": normalized_url, "new_tab": False}}],
                "max_failures": 2,
                "use_vision": use_vision,
            }

            # Set prompt mode: override (enhanced) or extend (wrapper)
            if use_override_mode:
                agent_kwargs["override_system_message"] = enhanced_prompt
            else:
                agent_kwargs["extend_system_message"] = prompt_wrapper

            try:
                signature = inspect.signature(Agent)
                has_kwargs = any(
                    param.kind is inspect.Parameter.VAR_KEYWORD
                    for param in signature.parameters.values()
                )
                if "register_new_step_callback" in signature.parameters:
                    agent_kwargs["register_new_step_callback"] = on_new_step

                # Handle browser-use version compatibility
                if use_override_mode:
                    # Using override mode - remove extend if not supported
                    if "extend_system_message" in agent_kwargs:
                        agent_kwargs.pop("extend_system_message")
                    if "override_system_message" not in signature.parameters and not has_kwargs:
                        # Fallback: override not supported, use extend instead
                        agent_kwargs.pop("override_system_message", None)
                        agent_kwargs["extend_system_message"] = prompt_wrapper
                        logger.warning(
                            "override_not_supported_fallback_to_extend",
                            extra={"session_id": session_id},
                        )
                else:
                    # Using extend mode - handle fallback to override if needed
                    if "extend_system_message" not in signature.parameters and not has_kwargs:
                        agent_kwargs.pop("extend_system_message", None)
                        if "override_system_message" in signature.parameters:
                            agent_kwargs["override_system_message"] = prompt_wrapper
                if "fallback_llm" not in signature.parameters and not has_kwargs:
                    agent_kwargs.pop("fallback_llm", None)
                if "initial_actions" not in signature.parameters and not has_kwargs:
                    agent_kwargs.pop("initial_actions", None)
                if "max_failures" not in signature.parameters and not has_kwargs:
                    agent_kwargs.pop("max_failures", None)
                # Only pass max_steps if explicitly set (env or client param)
                if effective_max_steps is not None:
                    if "max_steps" in signature.parameters or has_kwargs:
                        agent_kwargs["max_steps"] = effective_max_steps
                    else:
                        warnings.append(
                            "browser-use Agent does not support max_steps; value not enforced"
                        )
                # Only pass step_timeout if explicitly set (env or client param)
                if effective_step_timeout_s is not None:
                    if "step_timeout" in signature.parameters or has_kwargs:
                        agent_kwargs["step_timeout"] = effective_step_timeout_s
                    else:
                        warnings.append(
                            "browser-use Agent does not support step_timeout; value not enforced"
                        )
            except (TypeError, ValueError):
                pass

            agent = Agent(**agent_kwargs)
            register_callback = getattr(agent, "register_new_step_callback", None)
            if callable(register_callback):
                try:
                    callback_sig = inspect.signature(register_callback)
                    if len(callback_sig.parameters) == 1:
                        register_callback(on_new_step)
                except (TypeError, ValueError):
                    pass

            register_done_callback = getattr(agent, "register_done_callback", None)
            if callable(register_done_callback):
                try:
                    callback_sig = inspect.signature(register_done_callback)
                    if len(callback_sig.parameters) == 1:
                        register_done_callback(ensure_required_step_screenshots)
                except (TypeError, ValueError):
                    pass

            run_kwargs: dict[str, Any] = {}
            try:
                signature = inspect.signature(agent.run)
                has_kwargs = any(
                    param.kind is inspect.Parameter.VAR_KEYWORD
                    for param in signature.parameters.values()
                )
                if "on_step_end" in signature.parameters or has_kwargs:
                    run_kwargs["on_step_end"] = pause_gate
                # Only pass max_steps if explicitly set
                if effective_max_steps is not None:
                    if "max_steps" in signature.parameters or has_kwargs:
                        run_kwargs.setdefault("max_steps", effective_max_steps)
                # Only pass step_timeout if explicitly set
                if effective_step_timeout_s is not None:
                    if "step_timeout" in signature.parameters or has_kwargs:
                        run_kwargs.setdefault("step_timeout", effective_step_timeout_s)
            except (TypeError, ValueError):
                run_kwargs["on_step_end"] = pause_gate

            # Apply budget timeout to agent.run() execution only if explicitly set
            # Don't count setup overhead (browser creation, CDP, agent initialization)
            # against user's budget. If not set, let browser-use govern its own timeouts.
            async def run_agent() -> Any:
                return await agent.run(**run_kwargs)

            if effective_budget_s is not None:
                async with asyncio.timeout(effective_budget_s):
                    history = await run_agent()
            else:
                history = await run_agent()
        finally:
            cdp_attach_task.cancel()
            try:
                await cdp_attach_task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001
                logger.debug("Failed to wait for CDP attach task", exc_info=True)

            if streaming_attach_task is not None:
                streaming_attach_task.cancel()
                try:
                    await streaming_attach_task
                except asyncio.CancelledError:
                    pass
                except Exception:  # noqa: BLE001
                    logger.debug("Failed to wait for streaming attach task", exc_info=True)

            if cdp_streamer is not None:
                stop_streaming = getattr(cdp_streamer, "stop", None)
                if callable(stop_streaming):
                    try:
                        await asyncio.shield(stop_streaming(session_id=session_id))
                    except Exception:  # noqa: BLE001
                        logger.debug("Failed to stop streaming", exc_info=True)

            if cdp_attached:
                try:
                    cdp_client = getattr(browser_session, "cdp_client", None)
                    if cdp_client is not None:
                        cdp_capture.detach(cdp_client)
                except Exception:  # noqa: BLE001
                    logger.debug("Failed to detach CDP event capture", exc_info=True)

            if control_state is not None and active_session_set:
                clear_input_dispatcher = getattr(control_state, "clear_input_dispatcher", None)
                if callable(clear_input_dispatcher):
                    clear_input_dispatcher()
                clear_active_session = getattr(control_state, "clear_active_session", None)
                if callable(clear_active_session):
                    clear_active_session(session_id=session_id)

            if browser_session is not None:
                try:
                    await ensure_required_step_screenshots()
                except Exception:  # noqa: BLE001
                    logger.debug("Failed to guarantee step screenshots", exc_info=True)

            await asyncio.shield(stop_browser_session())

        if history is None:
            raise RuntimeError("browser-use run did not produce history")

        # Record validation and provider errors from history as agent events
        _record_history_errors_as_events(
            history=history,
            run_events=run_events,
            session_id=session_id,
            last_page_url=last_page_url,
            last_page_title=last_page_title,
        )
        try:
            from .optionb.run_event_artifacts import persist_run_events_from_store

            if run_events is not None:
                await persist_run_events_from_store(run_events, session_id=session_id)
        except Exception:  # noqa: BLE001
            pass

        raw_result = _normalize_history_result(_history_final_result(history))
        result, final_status, final_notes = _extract_wrapped_result(raw_result)
        error_count = _history_error_count(history)
        steps = _history_step_count(history)
        warnings.extend(_history_error_messages(history, max_items=8))
        if streaming_disabled_reason is not None:
            warnings.append(
                _truncate(f"streaming_disabled={streaming_disabled_reason}", max_len=400)
            )
        if final_notes is not None:
            warnings.append(_truncate(f"final_notes={final_notes}", max_len=400))
        warnings = _dedupe(warnings)[:20]

        timed_out = False
        if result is None:
            if (
                steps is not None
                and effective_max_steps is not None
                and steps >= effective_max_steps
            ):
                timed_out = True
            elif any("timeout" in warning.lower() for warning in warnings):
                timed_out = True

        status = "success" if result is not None else "failed"
        if final_status in {"login_required", "captcha", "impossible_task"}:
            if result is not None:
                status = "partial"
            warnings = _dedupe([*warnings, f"partial_reason={final_status}"])[:20]

        judgement = getattr(history, "judgement", None)
        if result is not None and callable(judgement):
            try:
                judgement_value = judgement()
            except Exception:  # noqa: BLE001
                judgement_value = None
            for flag, label in (
                ("impossible_task", "impossible_task"),
                ("reached_captcha", "reached_captcha"),
            ):
                value = (
                    getattr(judgement_value, flag, None) if judgement_value is not None else None
                )
                if isinstance(value, bool) and value:
                    status = "partial"
                    warnings = _dedupe([*warnings, f"partial_reason={label}"])[:20]
                    break

        summary = _truncate(
            (
                f"browser_use_steps={steps} "
                f"errors={error_count} "
                f"warnings={len(warnings)} "
                f"timed_out={timed_out}"
            ),
            max_len=2000,
        )

        page = {"url": _public_url(last_page_url), "title": last_page_title or None}
        errors_top = rank_failures_for_session(
            run_events=run_events,
            session_id=session_id,
            base_url=normalized_url,
            history=history,
            max_items=8,
        )
        stream_url = _build_stream_url(settings, session_id)
        payload = {
            "version": "gsd.web_eval_agent.v1",
            "session_id": session_id,
            "tool_call_id": tool_call_id,
            "url": normalized_url,
            "task": task,
            "mode": selected_mode,
            "requested_mode": str(mode) if mode is not None else None,
            "status": status,
            "result": result,
            "summary": summary,
            "stream_url": stream_url,
            "page": page,
            "errors_top": errors_top,
            "timeouts": {
                "budget_s": effective_budget_s,
                "step_timeout_s": effective_step_timeout_s,
                "max_steps": effective_max_steps,
                "timed_out": timed_out,
            },
            "warnings": warnings,
            "artifacts": {
                "screenshots": step_screenshot_count,
                "stream_samples": _count_stream_samples(),
                "run_events": (
                    getattr(run_events, "get_counts", lambda _sid: {"total": 0})(session_id).get(
                        "total", 0
                    )
                    if run_events is not None
                    else 0
                ),
            },
            "next_actions": [
                (
                    "Use get_screenshots(session_id="
                    f"'{session_id}', screenshot_type='agent_step', last_n=5)"
                ),
                (
                    "Use get_screenshots(session_id="
                    f"'{session_id}', screenshot_type='agent_step', include_images=false)"
                ),
                (
                    "Use get_run_events(session_id="
                    f"'{session_id}', event_types=['console','network'], has_error=true, last_n=50)"
                ),
                f"Open dashboard: http://{DEFAULT_DASHBOARD_HOST}:{DEFAULT_DASHBOARD_PORT}",
            ],
        }
        if selected_mode == "dev":
            payload["dev_excerpts"] = _dev_run_event_excerpts(
                run_events,
                session_id=session_id,
                base_url=normalized_url,
                history=history,
                max_per_type=5,
            )

        logger.info(
            "web_eval_agent completed",
            extra={
                "tool_call_id": tool_call_id,
                "session_id": session_id,
                "status": status,
                "duration_s": max(0.0, datetime.now(UTC).timestamp() - started),
                "result_present": result is not None,
                "errors": error_count,
            },
        )

        _terminate_session_in_registry(session_registry, session_id)
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
    except TimeoutError:
        duration_s = max(0.0, datetime.now(UTC).timestamp() - started)
        if effective_budget_s is not None:
            warnings = _dedupe([*warnings, f"timed_out_after_s={effective_budget_s:g}"])[:20]
            timeout_summary = _truncate(
                f"Timeout: tool budget exceeded (budget_s={effective_budget_s:g}).",
                max_len=2000,
            )
            next_actions = [
                "Increase budget_s (or reduce task scope) and retry.",
            ]
        else:
            warnings = _dedupe([*warnings, "timed_out"])[:20]
            timeout_summary = _truncate(
                "Timeout: browser start or operation exceeded an internal timeout. "
                "Try again, or increase TIMEOUT_BrowserStartEvent/TIMEOUT_BrowserLaunchEvent "
                "in the worker.",
                max_len=2000,
            )
            next_actions = [
                "Retry the tool call.",
                "If this consistently times out, increase TIMEOUT_BrowserStartEvent/"
                "TIMEOUT_BrowserLaunchEvent in the worker.",
            ]

        logger.info(
            "web_eval_agent timed out",
            extra={
                "tool_call_id": tool_call_id,
                "session_id": session_id,
                "url": normalized_url,
                "duration_s": duration_s,
            },
        )

        payload = {
            "version": "gsd.web_eval_agent.v1",
            "session_id": session_id,
            "tool_call_id": tool_call_id,
            "url": normalized_url,
            "task": task,
            "mode": selected_mode,
            "requested_mode": str(mode) if mode is not None else None,
            "status": "failed",
            "result": None,
            "summary": timeout_summary,
            "page": {"url": _public_url(last_page_url), "title": last_page_title or None},
            "errors_top": rank_failures_for_session(
                run_events=run_events,
                session_id=session_id,
                base_url=normalized_url,
                history=history,
                max_items=8,
            ),
            "timeouts": {
                "budget_s": effective_budget_s,
                "step_timeout_s": effective_step_timeout_s,
                "max_steps": effective_max_steps,
                "timed_out": True,
            },
            "warnings": warnings,
            "artifacts": {
                "screenshots": step_screenshot_count,
                "stream_samples": _count_stream_samples(),
                "run_events": (
                    getattr(run_events, "get_counts", lambda _sid: {"total": 0})(session_id).get(
                        "total", 0
                    )
                    if run_events is not None
                    else 0
                ),
            },
            "next_actions": [
                *next_actions,
                (
                    "Use get_run_events(session_id="
                    f"'{session_id}', event_types=['console','network'], has_error=true, last_n=50)"
                ),
                (
                    "Use get_screenshots(session_id="
                    f"'{session_id}', screenshot_type='agent_step', last_n=5)"
                ),
                f"Open dashboard: http://{DEFAULT_DASHBOARD_HOST}:{DEFAULT_DASHBOARD_PORT}",
            ],
        }
        _terminate_session_in_registry(session_registry, session_id)
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
    except asyncio.CancelledError:
        duration_s = max(0.0, datetime.now(UTC).timestamp() - started)
        warnings = _dedupe([*warnings, "cancelled"])[:20]

        logger.info(
            "web_eval_agent cancelled",
            extra={
                "tool_call_id": tool_call_id,
                "session_id": session_id,
                "url": normalized_url,
                "duration_s": duration_s,
            },
        )

        from .optionb.cancellation import should_propagate_cancelled_error

        if should_propagate_cancelled_error():
            raise

        payload = {
            "version": "gsd.web_eval_agent.v1",
            "session_id": session_id,
            "tool_call_id": tool_call_id,
            "url": normalized_url,
            "task": task,
            "mode": selected_mode,
            "requested_mode": str(mode) if mode is not None else None,
            "status": "failed",
            "result": None,
            "summary": _truncate("Cancelled.", max_len=2000),
            "page": {"url": _public_url(last_page_url), "title": last_page_title or None},
            "errors_top": rank_failures_for_session(
                run_events=run_events,
                session_id=session_id,
                base_url=normalized_url,
                history=history,
                max_items=8,
            ),
            "timeouts": {
                "budget_s": effective_budget_s,
                "step_timeout_s": effective_step_timeout_s,
                "max_steps": effective_max_steps,
                "timed_out": False,
            },
            "warnings": warnings,
            "artifacts": {
                "screenshots": step_screenshot_count,
                "stream_samples": _count_stream_samples(),
                "run_events": (
                    getattr(run_events, "get_counts", lambda _sid: {"total": 0})(session_id).get(
                        "total", 0
                    )
                    if run_events is not None
                    else 0
                ),
            },
            "next_actions": [
                "Retry the tool call.",
                f"Open dashboard: http://{DEFAULT_DASHBOARD_HOST}:{DEFAULT_DASHBOARD_PORT}",
            ],
        }
        _terminate_session_in_registry(session_registry, session_id)
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
    except Exception as exc:  # noqa: BLE001
        duration_s = max(0.0, datetime.now(UTC).timestamp() - started)
        warnings = _dedupe([*warnings, _truncate(f"{type(exc).__name__}: {exc}", max_len=400)])[:20]

        exc_type_name = type(exc).__name__
        exc_message = str(exc)
        is_validation_error = False
        is_provider_error = False

        if "validationerror" in exc_type_name.lower() or "pydantic" in exc_type_name.lower():
            is_validation_error = True
        elif any(
            keyword in exc_type_name.lower()
            for keyword in ["provider", "model", "llm", "openai", "anthropic", "ollama"]
        ):
            is_provider_error = True
        elif any(
            keyword in exc_message.lower()
            for keyword in [
                "validation",
                "invalid action",
                "schema",
                "provider",
                "api key",
                "rate limit",
                "model",
            ]
        ):
            if "validation" in exc_message.lower() or "invalid action" in exc_message.lower():
                is_validation_error = True
            else:
                is_provider_error = True

        if is_validation_error or is_provider_error:
            try:
                failure_type = "schema_validation" if is_validation_error else "provider_error"
                error_summary = _truncate(f"{failure_type}: {exc_type_name}", max_len=1000)
                record_agent_event_fn = getattr(run_events, "record_agent_event", None)
                if callable(record_agent_event_fn):
                    record_agent_event_fn(
                        session_id,
                        captured_at=datetime.now(UTC).timestamp(),
                        step=last_step_observed,
                        url=last_page_url,
                        title=last_page_title,
                        summary=error_summary,
                        has_error=True,
                    )
            except Exception:  # noqa: BLE001
                logger.debug("Failed to record agent error event", exc_info=True)

        logger.exception(
            "web_eval_agent failed",
            extra={
                "tool_call_id": tool_call_id,
                "session_id": session_id,
                "url": normalized_url,
                "duration_s": duration_s,
            },
        )
        payload = {
            "version": "gsd.web_eval_agent.v1",
            "session_id": session_id,
            "tool_call_id": tool_call_id,
            "url": normalized_url,
            "task": task,
            "mode": selected_mode,
            "requested_mode": str(mode) if mode is not None else None,
            "status": "failed",
            "result": None,
            "summary": _truncate(f"{type(exc).__name__}: {exc}", max_len=2000),
            "page": {"url": _public_url(last_page_url), "title": last_page_title or None},
            "errors_top": rank_failures_for_session(
                run_events=run_events,
                session_id=session_id,
                base_url=normalized_url,
                history=history,
                max_items=8,
            ),
            "timeouts": {
                "budget_s": effective_budget_s,
                "step_timeout_s": effective_step_timeout_s,
                "max_steps": effective_max_steps,
                "timed_out": False,
            },
            "warnings": warnings,
            "artifacts": {
                "screenshots": step_screenshot_count,
                "stream_samples": _count_stream_samples(),
                "run_events": (
                    getattr(run_events, "get_counts", lambda _sid: {"total": 0})(session_id).get(
                        "total", 0
                    )
                    if run_events is not None
                    else 0
                ),
            },
            "next_actions": [
                (
                    "Use get_run_events(session_id="
                    f"'{session_id}', event_types=['console','network'], has_error=true, last_n=50)"
                ),
                (
                    "Use get_screenshots(session_id="
                    f"'{session_id}', screenshot_type='agent_step', last_n=5)"
                ),
                f"Open dashboard: http://{DEFAULT_DASHBOARD_HOST}:{DEFAULT_DASHBOARD_PORT}",
            ],
        }
        _terminate_session_in_registry(session_registry, session_id)
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]


def _retag_web_eval_payload(
    response: list[TextContent], *, tool_name: str, version: str
) -> list[TextContent]:
    if not response:
        return response
    first = response[0]
    if getattr(first, "type", None) != "text":
        return response
    text = getattr(first, "text", None)
    if not isinstance(text, str) or not text.strip():
        return response
    try:
        payload = json.loads(text)
    except Exception:  # noqa: BLE001
        return response
    if not isinstance(payload, dict):
        return response
    payload["tool"] = tool_name
    payload["version"] = version
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]


@mcp.tool(name="web_task_agent")
async def web_task_agent(
    url: str,
    task: str,
    ctx: Context,
    headless_browser: bool = False,
    mode: str | None = None,
    budget_s: float | None = None,
    max_steps: int | None = None,
    step_timeout_s: float | None = None,
) -> list[TextContent]:
    """Run a short, safe browser workflow on a website.

    Use this tool for general web tasks (not limited to localhost). It is conservative:
    it avoids using any stored authenticated browser state by default, and it will stop
    if login/CAPTCHA is required.

    For authenticated workflows, first create a dedicated state file with:
      setup_browser_state(url=..., state_id="your_state")
    Then use a dedicated tool/workflow that is wired to that state_id (example:
    web_task_agent_github).
    """

    _ = ctx
    prompt_token = _PROMPT_PROFILE_OVERRIDE.set("web_task")
    state_token = _BROWSER_STATE_ID_OVERRIDE.set(None)
    try:
        response = await web_eval_agent(
            url=url,
            task=task,
            ctx=ctx,
            headless_browser=headless_browser,
            mode=mode,
            budget_s=budget_s,
            max_steps=max_steps,
            step_timeout_s=step_timeout_s,
        )
    finally:
        _PROMPT_PROFILE_OVERRIDE.reset(prompt_token)
        _BROWSER_STATE_ID_OVERRIDE.reset(state_token)

    return _retag_web_eval_payload(
        response, tool_name="web_task_agent", version="gsd.web_task_agent.v1"
    )


@mcp.tool(name="web_task_agent_github")
async def web_task_agent_github(
    url: str,
    task: str,
    ctx: Context,
    headless_browser: bool = False,
    mode: str | None = None,
    budget_s: float | None = None,
    max_steps: int | None = None,
    step_timeout_s: float | None = None,
) -> list[TextContent]:
    """Run a short browser workflow on GitHub using the dedicated `github` saved state.

    Prerequisite (one-time): run setup_browser_state(url="https://github.com/login",
    state_id="github")
    and complete login in the opened browser window.
    """

    _ = ctx
    prompt_token = _PROMPT_PROFILE_OVERRIDE.set("web_task")
    state_token = _BROWSER_STATE_ID_OVERRIDE.set("github")
    try:
        response = await web_eval_agent(
            url=url,
            task=task,
            ctx=ctx,
            headless_browser=headless_browser,
            mode=mode,
            budget_s=budget_s,
            max_steps=max_steps,
            step_timeout_s=step_timeout_s,
        )
    finally:
        _PROMPT_PROFILE_OVERRIDE.reset(prompt_token)
        _BROWSER_STATE_ID_OVERRIDE.reset(state_token)

    return _retag_web_eval_payload(
        response, tool_name="web_task_agent_github", version="gsd.web_task_agent_github.v1"
    )


def _coerce_int(value: Any | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _coerce_float(value: Any | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _coerce_bool(value: Any | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _coerce_video_size(value: Any | None) -> dict[str, int] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        width = _coerce_int(value.get("width"))
        height = _coerce_int(value.get("height"))
        if width and height and width > 0 and height > 0:
            return {"width": int(width), "height": int(height)}
    return None


def _mp4_snapshot(dir_path: str | None) -> dict[str, float]:
    if not dir_path:
        return {}
    try:
        root = Path(str(dir_path))
        root.mkdir(parents=True, exist_ok=True)
    except Exception:
        return {}
    items: dict[str, float] = {}
    try:
        for path in root.glob("*.mp4"):
            try:
                items[str(path)] = float(path.stat().st_mtime)
            except OSError:
                continue
    except Exception:
        return {}
    return items


def _mp4_diff_path(before: dict[str, float], after: dict[str, float]) -> str | None:
    created = [p for p in after.keys() if p not in before]
    if created:
        created.sort(key=lambda p: after.get(p, 0.0), reverse=True)
        return created[0]
    if after:
        candidates = sorted(after.keys(), key=lambda p: after.get(p, 0.0), reverse=True)
        return candidates[0]
    return None


def _extract_json_string_assignment(script: str, *, var_name: str) -> dict[str, Any] | None:
    # Looks for: VAR = r'''{...json...}''' or VAR = """..."""
    text = str(script)
    patterns = [
        rf"{re.escape(var_name)}\s*=\s*r?'''(.*?)'''",
        rf'{re.escape(var_name)}\s*=\s*r?"""(.*?)"""',
    ]
    for pat in patterns:
        match = re.search(pat, text, flags=re.DOTALL)
        if not match:
            continue
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            value = json.loads(raw)
        except Exception:
            continue
        if isinstance(value, dict):
            return value
    return None


async def _maybe_stop_browser_session(session: Any) -> None:
    stop = getattr(session, "stop", None)
    if not callable(stop):
        return
    try:
        result = stop()
        if inspect.isawaitable(result):
            await result
    except Exception:  # noqa: BLE001
        return


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


@mcp.tool(name="web_structured_flow")
async def web_structured_flow(
    record: dict[str, Any] | None = None,
    replay: dict[str, Any] | None = None,
    ctx: Context | None = None,
) -> list[TextContent]:
    """Record (LLM-assisted) and replay (LLM-free) structured browser flows.

    - record: uses browser-use Agent (or CodeAgent when available) + configured LLM provider to
      author a replayable Actor-API script
    - replay: executes the stored script (and optionally falls back to a deterministic DSL runner)
    """
    _ = ctx
    from .contracts.v1 import (
        ExportedScriptV1,
        RecordingInfoV1,
        TemplateInfoV1,
        WebStructuredFlowPayloadV1,
    )
    from .structured_flow_script import (
        build_replay_script_from_events,
        patch_exported_script,
        run_python_script,
        script_uses_llm_at_replay,
    )
    from .structured_flow_store import (
        base_origin_for_url,
        load_manifest,
        normalize_template_id,
        save_template_files,
        template_recordings_dir,
    )

    tool_call_id = uuid.uuid4()
    session_id = uuid.uuid4()
    warnings: list[str] = []

    if (record is None) == (replay is None):
        payload = WebStructuredFlowPayloadV1(
            version="gsd.web_structured_flow.v1",
            mode="record" if record is not None else "replay",
            session_id=session_id,
            tool_call_id=tool_call_id,
            status="failed",
            summary="Provide exactly one of record or replay.",
            url="",
            final_url=None,
            extracted=None,
            template=None,
            runner_used=None,
            runner_fallback_used=False,
            steps=[],
            script_logs=[],
            warnings=[],
            recording=None,
            exported_script=None,
        )
        text = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
        return [TextContent(type="text", text=text)]

    settings = load_settings(strict=False)

    def _patch_browser_use_cdp_wait_timeout() -> None:
        """Patch browser-use's LocalBrowserWatchdog CDP wait timeout if configured.

        browser-use 0.11.x hardcodes a 30s timeout in LocalBrowserWatchdog._wait_for_cdp_url().
        Some environments need longer for first-run browser startup.

        Configure via env var: GSD_STRUCTURED_FLOW_CDP_WAIT_TIMEOUT_S
        """

        raw = os.environ.get("GSD_STRUCTURED_FLOW_CDP_WAIT_TIMEOUT_S")
        if not raw:
            return
        try:
            timeout_s = float(str(raw).strip())
        except Exception:
            return
        if not (timeout_s and timeout_s > 0):
            return
        try:
            from browser_use.browser.watchdogs import (  # type: ignore[import-not-found]
                local_browser_watchdog,
            )
        except Exception:
            return
        cls = getattr(local_browser_watchdog, "LocalBrowserWatchdog", None)
        if cls is None:
            return
        orig = getattr(cls, "_wait_for_cdp_url", None)
        if not callable(orig) or getattr(orig, "_gsd_patched", False):
            return

        async def _wrapped_wait_for_cdp_url(port: int, timeout: float = 30) -> str:
            return await orig(port, timeout=float(timeout_s))

        _wrapped_wait_for_cdp_url._gsd_patched = True  # type: ignore[attr-defined]
        try:
            cls._wait_for_cdp_url = staticmethod(_wrapped_wait_for_cdp_url)  # type: ignore[assignment]
        except Exception:
            return

    try:
        if record is not None:
            raw_url = str(record.get("url") or "").strip()
            task = str(record.get("task") or "").strip()
            if not raw_url or not task:
                raise ValueError("record.url and record.task are required")
            url = _normalize_url(raw_url)

            template_id_raw = record.get("template_id") or uuid.uuid4().hex
            template_id = normalize_template_id(str(template_id_raw))
            template_name = str(record.get("template_name") or "").strip() or None
            state_id = record.get("state_id")
            headless = _coerce_bool(record.get("headless_browser"), default=False)
            enable_default_extensions = _coerce_bool(
                record.get("enable_default_extensions"), default=True
            )
            budget_s = _coerce_float(record.get("budget_s"))
            max_steps = _coerce_int(record.get("max_steps"))
            step_timeout_s = _coerce_float(record.get("step_timeout_s"))
            require_llm_free_replay = _coerce_bool(
                record.get("require_llm_free_replay"), default=True
            )
            settle_ms = _coerce_int(record.get("settle_ms")) or 100
            min_actions = _coerce_int(record.get("min_actions")) or 1
            strategy = str(record.get("strategy") or "auto").strip().lower()
            if strategy not in {"auto", "codeagent", "agent"}:
                strategy = "auto"

            record_llm_provider = str(record.get("llm_provider") or "").strip().lower() or None
            record_model = str(record.get("model") or "").strip() or None

            extract_fields: list[dict[str, Any]] | None = None
            extract_timing = str(record.get("extract_timing") or "before_last_click").strip()
            extract_after_action_index = _coerce_int(record.get("extract_after_action_index"))
            extract_block = record.get("extract")
            if isinstance(extract_block, dict):
                extract_timing = str(extract_block.get("timing") or extract_timing).strip()
                extract_after_action_index = _coerce_int(
                    extract_block.get("after_action_index")
                ) or extract_after_action_index
                fields = extract_block.get("fields")
                if isinstance(fields, list):
                    extract_fields = [f for f in fields if isinstance(f, dict)]
            fields_compat = record.get("extract_fields")
            if extract_fields is None and isinstance(fields_compat, list):
                extract_fields = [f for f in fields_compat if isinstance(f, dict)]

            record_video_dir = (
                str(record.get("record_video_dir")).strip()
                if record.get("record_video_dir")
                else str(template_recordings_dir(template_id))
            )
            record_video_size = _coerce_video_size(record.get("record_video_size"))
            record_video_framerate = _coerce_int(record.get("record_video_framerate"))

            before_mp4 = _mp4_snapshot(record_video_dir)

            storage_state: str | None = None
            if state_id is not None:
                path = _browser_state_path_for_id(str(state_id))
                if path.exists():
                    storage_state = str(path)
                else:
                    warnings.append(f"state_id provided but file missing: {path}")

            browser_executable_path = getattr(settings, "browser_executable_path", "") or None
            browser_kwargs: dict[str, object] = {
                "headless": headless,
                "storage_state": storage_state,
                "executable_path": browser_executable_path,
                "record_video_dir": record_video_dir,
                "enable_default_extensions": enable_default_extensions,
                "args": ["--remote-allow-origins=*"],
            }
            if record_video_size is not None:
                browser_kwargs["record_video_size"] = record_video_size
            if record_video_framerate is not None and record_video_framerate > 0:
                browser_kwargs["record_video_framerate"] = int(record_video_framerate)

            authoring_preamble = (
                "You are recording a browser automation template.\n"
                "IMPORTANT: This is a two-phase workflow:\n"
                "  - Phase A (now): you may use an LLM to decide actions.\n"
                "  - Phase B (future replay): the exported Python script MUST run without any "
                "LLM.\n"
                "\n"
                "Rules for replayability:\n"
                "- Use Actor API selectors and explicit waits.\n"
                "- Do NOT use *_by_prompt element finding.\n"
                "- Do NOT call extract(...).\n"
                "- Use page.evaluate with arrow-function JS when needed.\n"
                "- Do NOT write or edit files; ONLY use browser actions.\n\n"
                "Start URL:\n"
                f"{url}\n\n"
            )
            if strategy in {"codeagent"}:
                authoring_preamble += (
                    "If you are writing Python code during recording (CodeAgent path), ensure the "
                    "recorded code prints a single line:\n"
                    "  GSD_STRUCTURED_FLOW_RESULT=<json>\n"
                    'where json is {"final_url": "...", "extracted": {...}}.\n'
                    "Also define a Python string variable:\n"
                    "  GSD_FALLBACK_DSL_JSON = r'''{...json...}'''\n"
                    "containing a deterministic CSS-selector DSL for fallback.\n"
                )
            full_task = authoring_preamble + "\nUSER TASK:\n" + task

            patched_script: str | None = None
            uses_llm = False
            dsl_payload: dict[str, Any] | None = None

            _patch_browser_use_cdp_wait_timeout()

            # Strategy A: CodeAgent + session_to_python_script (requires ChatBrowserUse).
            if strategy in {"auto", "codeagent"}:
                try:
                    import browser_use  # type: ignore[import-not-found]
                    from browser_use.code_use import CodeAgent  # type: ignore[import-not-found]
                    from browser_use.code_use.notebook_export import (  # type: ignore[import-not-found]
                        session_to_python_script,
                    )

                    desired_model = str(getattr(settings, "model", "") or "").strip() or "bu-latest"
                    if not (
                        desired_model in {"bu-latest", "bu-1-0"}
                        or desired_model.startswith("browser-use/")
                        or desired_model.startswith("bu-")
                    ):
                        desired_model = "bu-latest"
                    llm_timeout_s = getattr(settings, "llm_timeout_s", None)
                    llm = browser_use.ChatBrowserUse(
                        model=desired_model,
                        api_key=settings.browser_use_api_key,
                        base_url=(
                            str(getattr(settings, "browser_use_llm_url", "") or "").strip()
                            or None
                        ),
                        timeout=float(llm_timeout_s) if llm_timeout_s is not None else 120.0,
                    )

                    agent = CodeAgent(task=full_task, llm=llm, **browser_kwargs)
                    if budget_s is not None and budget_s > 0:
                        session = await asyncio.wait_for(
                            agent.run(max_steps=max_steps),
                            timeout=float(budget_s),
                        )
                    else:
                        session = await agent.run(max_steps=max_steps)
                    _ = session
                    raw_script = session_to_python_script(agent)
                    candidate = patch_exported_script(raw_script)
                    if "GSD_STRUCTURED_FLOW_RESULT=" in candidate:
                        patched_script = candidate
                        dsl_payload = _extract_json_string_assignment(
                            patched_script, var_name="GSD_FALLBACK_DSL_JSON"
                        )
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"record_codeagent_failed: {type(exc).__name__}: {exc}")
                    if strategy == "codeagent":
                        raise

            # Strategy B: Agent-based record + event capture → generate script locally
            # (no CodeAgent required).
            if patched_script is None and strategy in {"auto", "agent"}:
                try:
                    from browser_use import Agent, BrowserSession  # type: ignore[import-not-found]
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        "browser-use is required for web_structured_flow(record=...). "
                        "Install gsd-browser with browser-use enabled."
                    ) from exc

                # Use the configured provider (OpenAI/Anthropic/etc.) for Agent record.
                from .llm.browser_use import create_browser_use_llms
                from .llm.env import normalize_llm_provider

                llm_timeout_s = getattr(settings, "llm_timeout_s", None)
                settings_for_record = settings
                if record_llm_provider or record_model:
                    update: dict[str, object] = {}
                    if record_llm_provider:
                        update["llm_provider"] = normalize_llm_provider(record_llm_provider)
                    if record_model:
                        update["model"] = record_model
                    settings_for_record = settings.model_copy(update=update)

                try:
                    llm = create_browser_use_llms(
                        settings_for_record, timeout_s=llm_timeout_s
                    ).primary
                except Exception as exc:  # noqa: BLE001
                    if record_llm_provider or record_model:
                        raise
                    # Practical default: if OPENAI_API_KEY is present but the configured
                    # provider is unusable, fall back to OpenAI with a sane default model.
                    if getattr(settings, "openai_api_key", ""):
                        settings_for_record = settings.model_copy(
                            update={"llm_provider": "openai", "model": "gpt-4o-mini"}
                        )
                        warnings.append(
                            "record_llm_fallback: using openai/gpt-4o-mini "
                            "(set GSD_LLM_PROVIDER/GSD_MODEL to override)"
                        )
                        llm = create_browser_use_llms(
                            settings_for_record, timeout_s=llm_timeout_s
                        ).primary
                    else:
                        raise exc

                browser_session = BrowserSession(**browser_kwargs)

                captured: list[dict[str, Any]] = []

                def _selector_from_node(node: Any) -> str | None:
                    if node is None:
                        return None
                    direct = getattr(node, "css_selector", None) or getattr(node, "selector", None)
                    if isinstance(direct, str) and direct.strip():
                        return direct.strip()
                    attrs = getattr(node, "attributes", None)
                    if not isinstance(attrs, dict):
                        attrs = {}
                    tag = str(getattr(node, "node_name", "") or "").lower() or None
                    for key in ("data-testid", "data-qa", "data-test", "data-cy", "data_testid"):
                        if key in attrs and str(attrs[key]).strip():
                            val = str(attrs[key]).strip()
                            return f'[{key}="{val}"]'
                    if "id" in attrs and str(attrs["id"]).strip():
                        return f"#{str(attrs['id']).strip()}"
                    if tag and "name" in attrs and str(attrs["name"]).strip():
                        val = str(attrs["name"]).strip()
                        return f'{tag}[name="{val}"]'
                    if tag and "aria-label" in attrs and str(attrs["aria-label"]).strip():
                        val = str(attrs["aria-label"]).strip()
                        return f'{tag}[aria-label="{val}"]'
                    return None

                event_bus = getattr(browser_session, "event_bus", None)
                on = getattr(event_bus, "on", None) if event_bus is not None else None
                if callable(on):
                    try:
                        from browser_use.browser.events import (  # type: ignore[import-not-found]
                            ClickElementEvent,
                            NavigateToUrlEvent,
                            SendKeysEvent,
                            TypeTextEvent,
                        )
                    except Exception:
                        ClickElementEvent = None  # type: ignore[assignment]
                        NavigateToUrlEvent = None  # type: ignore[assignment]
                        SendKeysEvent = None  # type: ignore[assignment]
                        TypeTextEvent = None  # type: ignore[assignment]

                    async def _capture_event(evt: Any) -> None:
                        name = type(evt).__name__
                        item: dict[str, Any] = {"type": name}
                        if name == "NavigateToUrlEvent":
                            item["url"] = getattr(evt, "url", None)
                        if name in {"ClickElementEvent", "TypeTextEvent"}:
                            node = getattr(evt, "node", None)
                            item["selector"] = _selector_from_node(node)
                            item["xpath"] = (
                                getattr(node, "xpath", None) if node is not None else None
                            )
                            if name == "TypeTextEvent":
                                is_sensitive = bool(getattr(evt, "is_sensitive", False))
                                if is_sensitive:
                                    key_name = str(
                                        getattr(evt, "sensitive_key_name", "") or ""
                                    ).strip()
                                    env_name = (
                                        f"GSD_STRUCTURED_FLOW_SECRET_{key_name.upper()}"
                                        if key_name
                                        else "GSD_STRUCTURED_FLOW_SECRET"
                                    )
                                    item["text"] = None
                                    item["text_env"] = env_name
                                else:
                                    item["text"] = getattr(evt, "text", None)
                        if name == "SendKeysEvent":
                            item["keys"] = getattr(evt, "keys", None)
                        captured.append(item)

                    for event_cls in (
                        NavigateToUrlEvent,
                        ClickElementEvent,
                        TypeTextEvent,
                        SendKeysEvent,
                    ):
                        if event_cls is None:
                            continue
                        try:
                            on(event_cls, _capture_event)
                        except Exception:
                            continue

                try:
                    _patch_browser_use_cdp_wait_timeout()
                    await _maybe_await(browser_session.start())

                    use_vision_raw = str(
                        record.get("use_vision")
                        if record.get("use_vision") is not None
                        else getattr(settings_for_record, "use_vision", "auto")
                    ).strip().lower()
                    use_vision: bool | str
                    if use_vision_raw in {"true", "1", "yes", "y", "on"}:
                        use_vision = True
                    elif use_vision_raw in {"false", "0", "no", "n", "off"}:
                        use_vision = False
                    else:
                        use_vision = "auto"

                    agent_kwargs: dict[str, Any] = {
                        "task": full_task,
                        "llm": llm,
                        "browser_session": browser_session,
                        "use_vision": use_vision,
                        "initial_actions": [
                            {"navigate": {"url": url, "new_tab": False}},
                        ],
                    }
                    try:
                        from browser_use import Tools  # type: ignore[import-not-found]

                        agent_kwargs["tools"] = Tools(
                            exclude_actions=[
                                "write_file",
                                "read_file",
                                "replace_file",
                                "extract",
                                "search",
                                "find_text",
                                "retry_with_browser_use_agent",
                            ]
                        )
                        agent_kwargs["enable_planning"] = False
                    except Exception:
                        pass
                    try:
                        agent = Agent(**agent_kwargs)
                    except TypeError:
                        agent_kwargs.pop("initial_actions", None)
                        try:
                            agent = Agent(**agent_kwargs)
                        except TypeError:
                            if "tools" in agent_kwargs and "controller" not in agent_kwargs:
                                agent_kwargs["controller"] = agent_kwargs.pop("tools")
                                try:
                                    agent = Agent(**agent_kwargs)
                                except TypeError:
                                    agent_kwargs.pop("controller", None)
                                    agent_kwargs.pop("enable_planning", None)
                                    agent_kwargs.pop("use_vision", None)
                                    agent = Agent(**agent_kwargs)
                            else:
                                agent_kwargs.pop("enable_planning", None)
                                agent_kwargs.pop("tools", None)
                                agent_kwargs.pop("controller", None)
                                agent_kwargs.pop("use_vision", None)
                                agent = Agent(**agent_kwargs)
                    if budget_s is not None and budget_s > 0:
                        await asyncio.wait_for(
                            agent.run(max_steps=max_steps),
                            timeout=float(budget_s),
                        )
                    else:
                        await agent.run(max_steps=max_steps)

                    action_count = sum(
                        1
                        for evt in captured
                        if evt.get("type")
                        in {
                            "ClickElementEvent",
                            "TypeTextEvent",
                            "SendKeysEvent",
                        }
                        and (
                            evt.get("keys") is not None
                            or evt.get("selector") is not None
                            or evt.get("xpath") is not None
                        )
                    )
                    if action_count < min_actions:
                        raise RuntimeError(
                            f"Captured too few actions ({action_count}); "
                            f"expected at least {min_actions}."
                        )

                    default_step_timeout_ms = (
                        int(float(step_timeout_s) * 1000.0)
                        if step_timeout_s is not None and step_timeout_s > 0
                        else 30_000
                    )
                    patched_script, dsl_payload = build_replay_script_from_events(
                        events=captured,
                        default_extract_fields=extract_fields,
                        extract_timing=extract_timing,
                        extract_after_action_index=extract_after_action_index,
                        settle_ms=settle_ms,
                        default_step_timeout_ms=default_step_timeout_ms,
                    )
                    uses_llm = False
                finally:
                    await _maybe_stop_browser_session(browser_session)

            if patched_script is None:
                raise RuntimeError("Record failed: no script generated.")

            if "GSD_STRUCTURED_FLOW_RESULT=" not in patched_script:
                raise RuntimeError(
                    "Record run did not produce a replay result marker. "
                    "Expected the exported script to print GSD_STRUCTURED_FLOW_RESULT=...."
                )

            uses_llm, reasons = script_uses_llm_at_replay(patched_script)
            if uses_llm:
                warnings.append("script_replay_llm_scan: " + "; ".join(reasons))
                if require_llm_free_replay:
                    raise RuntimeError(
                        "Exported script appears to require LLM at replay time: "
                        + "; ".join(reasons)
                    )

            if dsl_payload is None:
                warnings.append("No GSD_FALLBACK_DSL_JSON found; DSL fallback unavailable.")

            base_origin = base_origin_for_url(url)
            manifest = save_template_files(
                template_id=template_id,
                template_name=template_name,
                base_origin=base_origin,
                recorded_example_url=url,
                script_content=patched_script,
                uses_llm_at_replay=uses_llm,
                dsl_payload=dsl_payload,
            )

            after_mp4 = _mp4_snapshot(record_video_dir)
            mp4_path = _mp4_diff_path(before_mp4, after_mp4)
            recording = RecordingInfoV1(
                enabled=True,
                dir=record_video_dir,
                path=mp4_path,
                available=bool(mp4_path),
                warning=(
                    None
                    if mp4_path
                    else "No mp4 detected (missing deps or recording disabled)."
                ),
                size=record_video_size,
                framerate=record_video_framerate,
            )

            template_info = TemplateInfoV1(
                template_id=manifest.template_id,
                template_name=manifest.template_name,
                base_origin=manifest.base_origin,
                created_at=manifest.created_at,
                updated_at=manifest.updated_at,
                script_path=manifest.script_path,
                dsl_path=manifest.dsl_path,
                manifest_path=manifest.manifest_path,
                sha256=manifest.sha256,
                uses_llm_at_replay=manifest.uses_llm_at_replay,
            )

            payload = WebStructuredFlowPayloadV1(
                version="gsd.web_structured_flow.v1",
                mode="record",
                session_id=session_id,
                tool_call_id=tool_call_id,
                status="success",
                summary="Recorded flow and exported replay script.",
                url=url,
                final_url=None,
                extracted=None,
                template=template_info,
                runner_used=None,
                runner_fallback_used=False,
                steps=[],
                script_logs=[],
                warnings=warnings,
                recording=recording,
                exported_script=ExportedScriptV1(language="python", content=patched_script),
            )
            return [
                TextContent(
                    type="text",
                    text=json.dumps(payload.model_dump(mode="json"), ensure_ascii=False),
                )
            ]

        # replay
        assert replay is not None
        raw_url = str(replay.get("url") or "").strip()
        template_id = normalize_template_id(str(replay.get("template_id") or "").strip())
        if not raw_url or not template_id:
            raise ValueError("replay.template_id and replay.url are required")
        url = _normalize_url(raw_url)
        runner = str(replay.get("runner") or "script_then_dsl").strip().lower()
        if runner not in {"script", "dsl", "script_then_dsl"}:
            runner = "script_then_dsl"

        state_id = replay.get("state_id")
        headless = _coerce_bool(replay.get("headless_browser"), default=True)
        enable_default_extensions = _coerce_bool(
            replay.get("enable_default_extensions"), default=True
        )
        budget_s = _coerce_float(replay.get("budget_s"))
        step_timeout_s = _coerce_float(replay.get("step_timeout_s"))
        settle_ms = int(replay.get("settle_ms") or 100)

        record_video_dir = str(replay.get("record_video_dir") or "").strip() or None
        record_video_size = _coerce_video_size(replay.get("record_video_size"))
        record_video_framerate = _coerce_int(replay.get("record_video_framerate"))

        manifest = load_manifest(template_id)
        url_origin = base_origin_for_url(url)
        if url_origin != manifest.base_origin:
            raise ValueError(
                f"URL origin mismatch: expected {manifest.base_origin}, got {url_origin}"
            )

        storage_state: str | None = None
        if state_id is not None:
            path = _browser_state_path_for_id(str(state_id))
            if path.exists():
                storage_state = str(path)
            else:
                warnings.append(f"state_id provided but file missing: {path}")

        template_info = TemplateInfoV1(
            template_id=manifest.template_id,
            template_name=manifest.template_name,
            base_origin=manifest.base_origin,
            created_at=manifest.created_at,
            updated_at=manifest.updated_at,
            script_path=manifest.script_path,
            dsl_path=manifest.dsl_path,
            manifest_path=manifest.manifest_path,
            sha256=manifest.sha256,
            uses_llm_at_replay=manifest.uses_llm_at_replay,
        )

        script_logs: list[str] = []
        final_url: str | None = None
        extracted: dict[str, Any] | None = None
        step_results: list[dict[str, Any]] = []
        runner_used: Literal["script", "dsl"] | None = None
        fallback_used = False

        recording: RecordingInfoV1 | None = None
        if record_video_dir:
            before_mp4 = _mp4_snapshot(record_video_dir)
        else:
            before_mp4 = {}

        def _finalize_recording() -> RecordingInfoV1 | None:
            if not record_video_dir:
                return None
            after = _mp4_snapshot(record_video_dir)
            mp4_path = _mp4_diff_path(before_mp4, after)
            return RecordingInfoV1(
                enabled=True,
                dir=record_video_dir,
                path=mp4_path,
                available=bool(mp4_path),
                warning=(
                    None
                    if mp4_path
                    else "No mp4 detected (missing deps or recording disabled)."
                ),
                size=record_video_size,
                framerate=record_video_framerate,
            )

        script_ok = False
        script_result: dict[str, Any] | None = None
        if runner in {"script", "script_then_dsl"}:
            res = run_python_script(
                script_path=Path(manifest.script_path),
                target_url=url,
                storage_state_path=storage_state,
                headless=headless,
                enable_default_extensions=enable_default_extensions,
                record_video_dir=record_video_dir,
                record_video_size=record_video_size,
                record_video_framerate=record_video_framerate,
                timeout_s=budget_s,
            )
            script_logs = res.logs
            script_ok = res.ok and isinstance(res.result, dict)
            script_result = res.result if isinstance(res.result, dict) else None
            if script_ok and script_result is not None:
                runner_used = "script"
                final_url = (
                    str(script_result.get("final_url"))
                    if script_result.get("final_url")
                    else None
                )
                extracted_val = script_result.get("extracted")
                if isinstance(extracted_val, dict):
                    extracted = extracted_val

        if (not script_ok) and runner in {"dsl", "script_then_dsl"}:
            dsl_path = manifest.dsl_path
            if dsl_path:
                try:
                    dsl_payload = json.loads(Path(dsl_path).read_text(encoding="utf-8"))
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"Failed to load DSL: {type(exc).__name__}: {exc}")
                    dsl_payload = None
            else:
                dsl_payload = None

            if dsl_payload is None:
                if runner == "dsl":
                    raise RuntimeError("No DSL available for this template.")
            else:
                fallback_used = script_ok is False and runner == "script_then_dsl"
                from .structured_flow import run_dsl_flow

                try:
                    from browser_use import (  # type: ignore[import-not-found]
                        BrowserProfile,
                        BrowserSession,
                    )
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        "browser-use is required for DSL replay. "
                        "Install gsd-browser with browser-use."
                    ) from exc

                browser_executable_path = getattr(settings, "browser_executable_path", "") or None
                browser_kwargs: dict[str, object] = {
                    "headless": headless,
                    "storage_state": storage_state,
                    "executable_path": browser_executable_path,
                    "enable_default_extensions": enable_default_extensions,
                    "args": ["--remote-allow-origins=*"],
                }
                if record_video_dir:
                    browser_kwargs["record_video_dir"] = record_video_dir
                if record_video_size is not None:
                    browser_kwargs["record_video_size"] = record_video_size
                if record_video_framerate is not None and record_video_framerate > 0:
                    browser_kwargs["record_video_framerate"] = int(record_video_framerate)

                browser_session: Any | None = None
                try:
                    try:
                        browser_session = BrowserSession(**browser_kwargs)
                    except TypeError:
                        profile = BrowserProfile(**browser_kwargs)
                        browser_session = BrowserSession(browser_profile=profile)

                    start = getattr(browser_session, "start", None)
                    if callable(start):
                        _patch_browser_use_cdp_wait_timeout()
                        await _maybe_await(start())

                    new_page = getattr(browser_session, "new_page", None)
                    if not callable(new_page):
                        raise RuntimeError("BrowserSession.new_page is unavailable")
                    page = await _maybe_await(new_page(url))

                    steps = dsl_payload.get("steps") if isinstance(dsl_payload, dict) else None
                    if not isinstance(steps, list):
                        raise RuntimeError("DSL must include steps: list")

                    final_url, extracted_out, step_results = await run_dsl_flow(
                        browser=browser_session,
                        page=page,
                        steps=steps,
                        step_timeout_s=step_timeout_s,
                        settle_ms=settle_ms,
                    )
                    extracted = extracted_out
                    runner_used = "dsl"
                finally:
                    if browser_session is not None:
                        await _maybe_stop_browser_session(browser_session)

        recording = _finalize_recording()

        status: Literal["success", "failed", "partial"]
        if runner_used is not None and (final_url is not None or extracted is not None):
            status = "success"
            summary = "Replayed flow."
        elif runner_used is not None:
            status = "partial"
            summary = "Ran replay but could not parse a structured result."
        else:
            status = "failed"
            summary = "Replay failed."

        payload = WebStructuredFlowPayloadV1(
            version="gsd.web_structured_flow.v1",
            mode="replay",
            session_id=session_id,
            tool_call_id=tool_call_id,
            status=status,
            summary=summary,
            url=url,
            final_url=final_url,
            extracted=extracted,
            template=template_info,
            runner_used=runner_used,
            runner_fallback_used=fallback_used,
            steps=step_results,  # type: ignore[arg-type]
            script_logs=script_logs,
            warnings=warnings,
            recording=recording,
            exported_script=None,
        )
        text = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
        return [TextContent(type="text", text=text)]
    except Exception as exc:  # noqa: BLE001
        failed_url = ""
        if record or replay:
            failed_url = _normalize_url(str((record or replay or {}).get("url") or ""))
        payload = WebStructuredFlowPayloadV1(
            version="gsd.web_structured_flow.v1",
            mode="record" if record is not None else "replay",
            session_id=session_id,
            tool_call_id=tool_call_id,
            status="failed",
            summary=_truncate(f"{type(exc).__name__}: {exc}", max_len=2048),
            url=failed_url,
            final_url=None,
            extracted=None,
            template=None,
            runner_used=None,
            runner_fallback_used=False,
            steps=[],
            script_logs=[],
            warnings=warnings,
            recording=None,
            exported_script=None,
        )
        text = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
        return [TextContent(type="text", text=text)]


@mcp.tool(name="get_run_events")
async def get_run_events(
    session_id: str = "",
    last_n: int = 50,
    event_types: list[str] | None = None,
    from_timestamp: Any | None = None,
    has_error: bool | None = None,
    include_details: bool = False,
    ctx: Context | None = None,
) -> list[TextContent]:
    """Retrieve stored run events for web_eval_agent sessions as a JSON payload.

    This tool is designed to keep web_eval_agent responses compact while still allowing
    clients to fetch detailed console/network/agent events on demand.

    Args:
        session_id: Filter to a single session_id (required; UUID string).
        last_n: Max number of events to return (default 50, max 200).
        event_types: Optional list of event types ("agent", "console", "network").
        from_timestamp: Only include events after this timestamp (epoch seconds or ISO-8601).
        has_error: Filter for events marked as errors (optional).
        include_details: Whether to include event details payloads (default false).

    Returns:
        list[TextContent]: A single JSON payload encoded as text.
    """
    _ = ctx
    runtime = get_runtime()
    run_events = getattr(runtime, "run_events", None)

    try:
        parsed_session_id = uuid.UUID(str(session_id))
        if parsed_session_id.version != 4:
            raise ValueError("session_id must be UUIDv4")
    except (TypeError, ValueError):
        payload = {
            "version": "gsd.get_run_events.v1",
            "session_id": None,
            "events": [],
            "stats": {
                "counts": {"agent": 0, "console": 0, "network": 0, "total": 0},
                "oldest_timestamp": None,
                "newest_timestamp": None,
            },
            "error": "session_id is required and must be a UUID string.",
        }
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]

    last_n_value = min(max(int(last_n), 0), 200)

    normalized_types: list[str] | None = None
    error: str | None = None
    if event_types is not None:
        normalized: list[str] = []
        invalid: set[str] = set()
        for item in event_types:
            candidate = str(item).strip().lower()
            if not candidate:
                continue
            if candidate not in _RUN_EVENT_TYPES:
                invalid.add(candidate)
                continue
            if candidate not in normalized:
                normalized.append(candidate)
        if invalid:
            error = (
                f"Invalid event_types={sorted(invalid)}. "
                f"Expected subset of {sorted(_RUN_EVENT_TYPES)}."
            )
        else:
            normalized_types = normalized or None

    parsed_from_timestamp = _parse_timestamp(from_timestamp)
    if error is None and from_timestamp is not None and parsed_from_timestamp is None:
        error = "from_timestamp must be epoch seconds or ISO-8601 timestamp."

    if error is not None:
        payload = {
            "version": "gsd.get_run_events.v1",
            "session_id": None,
            "events": [],
            "stats": {
                "counts": {"agent": 0, "console": 0, "network": 0, "total": 0},
                "oldest_timestamp": None,
                "newest_timestamp": None,
            },
            "error": error,
        }
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]

    used_distributed = False
    events: list[dict[str, Any]] = []

    try:
        from .optionb.azure_blob_client import has_azure_blob_config
    except ImportError:
        has_azure_blob_config = None  # type: ignore[assignment]

    try:
        from .optionb.s3_client import has_complete_s3_config
    except ImportError:
        has_complete_s3_config = None  # type: ignore[assignment]

    azure_available = bool(has_azure_blob_config() if callable(has_azure_blob_config) else False)
    s3_available = bool(has_complete_s3_config() if callable(has_complete_s3_config) else False)

    if azure_available or s3_available:
        try:
            from .optionb.artifact_index import get_artifact_index_store
            from .optionb.azure_blob_client import get_azure_blob_client
            from .optionb.identity import STDIO_IDENTITY
            from .optionb.request_context import get_current_identity
            from .optionb.s3_client import get_s3_client

            identity = get_current_identity() or STDIO_IDENTITY
            store = get_artifact_index_store()
            docket = store.docket_getter()
            if docket is not None:
                used_distributed = True
                s3 = get_s3_client() if s3_available else None
                azure = get_azure_blob_client() if azure_available else None
                zset_key = (
                    f"gsd:v1:tenants:{identity.tenant_id}:subjects:{identity.subject_id}"
                    f":sessions:{session_id}:run_events:z"
                )
                candidate_limit = 50
                min_score: int | None = None
                if parsed_from_timestamp is not None:
                    min_score = int(float(parsed_from_timestamp) * 1000)
                async with docket.redis() as client:
                    if min_score is None:
                        candidates = await client.zrevrange(zset_key, 0, candidate_limit - 1)
                    else:
                        candidates = await client.zrevrangebyscore(
                            zset_key, "+inf", min_score, start=0, num=candidate_limit
                        )

                for raw in candidates:
                    artifact_id = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                    try:
                        parsed = uuid.UUID(str(artifact_id))
                        if parsed.version != 4:
                            continue
                    except (TypeError, ValueError):
                        continue

                    record = await store.get_meta(artifact_id)
                    if record is None or record.state != "ready":
                        continue
                    if record.artifact_kind != "run_event_chunk":
                        continue
                    if has_error is True and not bool(record.has_error):
                        continue

                    try:
                        backend = record.get_effective_backend()
                    except Exception:  # noqa: BLE001
                        continue

                    body: bytes = b""
                    try:
                        if backend == "azure":
                            if azure is None:
                                continue
                            body = azure.get_bytes(blob_name=record.s3_key)
                        else:
                            if s3 is None:
                                continue
                            body = s3.get_bytes(key=record.s3_key)
                    except Exception:  # noqa: BLE001
                        continue
                    if not body:
                        continue

                    try:
                        text = body.decode("utf-8")
                    except Exception:  # noqa: BLE001
                        continue

                    for line in text.splitlines():
                        stripped = line.strip()
                        if not stripped:
                            continue
                        try:
                            event = json.loads(stripped)
                        except Exception:  # noqa: BLE001
                            continue
                        if not isinstance(event, dict):
                            continue

                        event_type_value = event.get("event_type") or event.get("type")
                        if not isinstance(event_type_value, str):
                            continue
                        event_type_value = event_type_value.strip()
                        if normalized_types and event_type_value not in normalized_types:
                            continue

                        ts = event.get("timestamp")
                        if ts is None:
                            ts = event.get("captured_at")
                        if parsed_from_timestamp is not None and isinstance(ts, (int, float)):
                            if float(ts) < float(parsed_from_timestamp):
                                continue

                        if has_error is not None:
                            if bool(event.get("has_error")) is not bool(has_error):
                                continue

                        item = dict(event)
                        if not include_details:
                            item.pop("details", None)
                            item.pop("location", None)
                        events.append(item)
                        if len(events) >= last_n_value:
                            break

                    if len(events) >= last_n_value:
                        break
        except Exception:  # noqa: BLE001
            used_distributed = False
            events = []

    if not used_distributed:
        get_events = getattr(run_events, "get_events", None) if run_events is not None else None
        if callable(get_events):
            events = get_events(
                session_id=session_id,
                last_n=last_n_value,
                event_types=normalized_types,
                from_timestamp=parsed_from_timestamp,
                has_error=has_error,
                include_details=bool(include_details),
            )
        else:
            events = []

    counts: dict[str, int] = {"agent": 0, "console": 0, "network": 0, "total": len(events)}
    timestamps: list[float] = []
    for event in events:
        event_type_value = event.get("event_type") or event.get("type")
        if isinstance(event_type_value, str) and event_type_value in counts:
            counts[event_type_value] += 1
        timestamp_value = event.get("timestamp")
        if timestamp_value is None:
            timestamp_value = event.get("captured_at")
        if isinstance(timestamp_value, (int, float)):
            timestamps.append(float(timestamp_value))

    payload = {
        "version": "gsd.get_run_events.v1",
        "session_id": session_id,
        "events": events[:last_n_value],
        "stats": {
            "counts": counts,
            "oldest_timestamp": min(timestamps) if timestamps else None,
            "newest_timestamp": max(timestamps) if timestamps else None,
        },
        "error": None,
    }

    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]


@mcp.tool(name="setup_browser_state")
async def setup_browser_state(
    url: str | None = None,
    state_id: str | None = None,
    ctx: Context | None = None,
) -> list[TextContent]:
    """Sets up and saves browser state for future use.

    This tool should only be called in one scenario:
    1. The user explicitly requests to set up browser state/authentication

    Launches a non-headless browser for user interaction, allows login/authentication,
    and saves the browser state (cookies, local storage, etc.) to a local file.

    Args:
        url: Optional URL to navigate to upon opening the browser.
        state_id: Optional browser state identifier. Use distinct IDs to keep separate
            authenticated sessions (e.g. "github", "google"). If unset, uses the default
            path `~/.gsd/browser_state/state.json`.
        ctx: The MCP context (used for progress reporting, not directly here).

    Returns:
        list[TextContent]: Confirmation of state saving or error messages.
    """
    _ = ctx
    runtime = get_runtime()
    settings = load_settings(strict=False)
    bind_host = getattr(settings, "streaming_bind_host", "") or DEFAULT_DASHBOARD_HOST
    runtime.ensure_dashboard_running(
        settings=settings, host=bind_host, port=DEFAULT_DASHBOARD_PORT
    )

    tool_call_id = str(uuid.uuid4())
    normalized_url = _normalize_url(url) if url else None
    try:
        state_path = (
            _browser_state_path_for_id(state_id)
            if state_id is not None
            else _browser_state_path()
        )
    except ValueError as exc:
        return [TextContent(type="text", text=f"Invalid state_id: {exc}")]
    state_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "setup_browser_state called",
        extra={
            "tool_call_id": tool_call_id,
            "url": normalized_url,
            "state_id": state_id,
            "state_path": str(state_path),
        },
    )

    try:
        state_path = await capture_state_interactive(url=normalized_url, state_id=state_id)

        payload = {
            "version": "gsd.setup_browser_state.v1",
            "status": "success",
            "state_id": state_id,
            "url": normalized_url,
            "path": str(state_path),
            "summary": "Saved browser state.",
            "next_actions": [
                (
                    "Use setup_browser_state(url=..., state_id=...) to refresh it if the session "
                    "expires."
                ),
            ],
        }
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        payload = {
            "version": "gsd.setup_browser_state.v1",
            "status": "failed",
            "state_id": state_id,
            "url": normalized_url,
            "path": None,
            "summary": _truncate(f"Error executing setup_browser_state: {exc}", max_len=2000),
            "traceback": tb,
            "next_actions": [
                "Retry setup_browser_state(url=..., state_id=...) in an interactive environment.",
            ],
        }
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]


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
    """Retrieve screenshots from evaluation sessions.

    Screenshots are automatically captured during web_eval_agent executions at key moments
    (agent steps) and periodically during browser streaming. This tool allows you to
    retrieve them without token overflow issues. The dashboard at port 5009 shows all
    screenshots in real-time, while this tool provides programmatic access.

    Args:
        last_n: Number of most recent screenshots (default: 5, max: 20)
        screenshot_type: Filter by type - "agent_step", "stream_sample", or "all"
        session_id: Filter by specific session (required; UUID string)
        from_timestamp: Only get screenshots after this time
        has_error: Filter for error screenshots only
        include_images: If False, return metadata only

    Returns:
        Screenshot data or metadata with debugging information
    """
    _ = ctx
    runtime = get_runtime()
    last_n = min(max(last_n, 0), 20)
    stats = runtime.screenshots.get_stats()

    normalized_type = str(screenshot_type).strip().lower()
    if normalized_type not in {"agent_step", "stream_sample", "all"}:
        normalized_type = "agent_step"

    def _delivery_mode() -> str:
        raw = str(os.environ.get("GSD_ARTIFACT_DELIVERY_MODE", "inline")).strip().lower()
        return raw if raw in {"inline", "presigned", "both"} else "inline"
    from .optionb.artifact_delivery import presigned_url_ttl_s_from_env

    delivery_mode = _delivery_mode()
    include_presigned = delivery_mode in {"presigned", "both"}

    try:
        parsed_session_id = uuid.UUID(str(session_id))
        if parsed_session_id.version != 4:
            raise ValueError("session_id must be UUIDv4")
    except (TypeError, ValueError):
        payload = {
            "version": "gsd.get_screenshots.v1",
            "session_id": None,
            "filters": {
                "last_n": last_n,
                "screenshot_type": normalized_type,
                "from_timestamp": from_timestamp,
                "has_error": has_error,
                "include_images": include_images,
            },
            "screenshots": [],
            "stats": stats,
            "error": "session_id is required and must be a UUID string.",
        }
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]

    header_screenshots: list[dict[str, Any]] = []
    inline_images: list[ImageContent] = []
    error: str | None = None
    used_distributed = False

    try:
        from .optionb.artifact_index import get_artifact_index_store
        from .optionb.identity import STDIO_IDENTITY
        from .optionb.request_context import get_current_identity
    except Exception:  # noqa: BLE001
        pass
    else:
        try:
            identity = get_current_identity() or STDIO_IDENTITY
            store = get_artifact_index_store()
            docket = store.docket_getter()
            if docket is not None:
                used_distributed = True

                s3 = None
                try:
                    from .optionb.s3_client import get_s3_client, has_complete_s3_config

                    if has_complete_s3_config():
                        s3 = get_s3_client()
                except Exception:  # noqa: BLE001
                    s3 = None

                azure_client = None
                try:
                    from .optionb.azure_blob_client import (
                        get_azure_blob_client,
                        has_azure_blob_config,
                    )

                    if has_azure_blob_config():
                        azure_client = get_azure_blob_client()
                except Exception:  # noqa: BLE001
                    azure_client = None

                zset_key = (
                    f"gsd:v1:tenants:{identity.tenant_id}:subjects:{identity.subject_id}"
                    f":sessions:{session_id}:screenshots:z"
                )
                candidate_limit = min(max(last_n * 10, 50), 200)
                min_score: int | None = None
                if from_timestamp is not None:
                    min_score = int(float(from_timestamp) * 1000)
                async with docket.redis() as client:
                    if min_score is None:
                        candidates = await client.zrevrange(zset_key, 0, candidate_limit - 1)
                    else:
                        candidates = await client.zrevrangebyscore(
                            zset_key, "+inf", min_score, start=0, num=candidate_limit
                        )

                ttl_s = presigned_url_ttl_s_from_env()
                for raw in candidates:
                    artifact_id = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                    try:
                        parsed = uuid.UUID(str(artifact_id))
                        if parsed.version != 4:
                            continue
                    except (TypeError, ValueError):
                        continue

                    record = await store.get_meta(artifact_id)
                    if record is None or record.state != "ready":
                        continue
                    if record.artifact_kind != "screenshot":
                        continue
                    if normalized_type != "all" and record.screenshot_type != normalized_type:
                        continue
                    if has_error is not None and bool(record.has_error) != bool(has_error):
                        continue

                    backend = "s3"
                    try:
                        backend = str(record.get_effective_backend())
                    except Exception:  # noqa: BLE001
                        backend = "s3"

                    inline_included = False
                    image_base64: str | None = None
                    want_inline = bool(
                        include_images
                        and (delivery_mode in {"inline", "both"} or backend == "redis")
                    )
                    if want_inline:
                        image_bytes = b""
                        if backend == "redis":
                            try:
                                async with docket.redis() as client:
                                    raw_bytes = await client.get(str(record.s3_key))
                                if isinstance(raw_bytes, bytes):
                                    image_bytes = raw_bytes
                                elif isinstance(raw_bytes, str):
                                    image_bytes = raw_bytes.encode("utf-8")
                            except Exception:  # noqa: BLE001
                                image_bytes = b""
                        elif backend == "azure":
                            if azure_client is None:
                                if error is None:
                                    error = (
                                        "Azure artifacts require GSD_AZURE_STORAGE_ACCOUNT "
                                        "(and Container App managed identity RBAC) to retrieve."
                                    )
                            else:
                                try:
                                    image_bytes = azure_client.get_bytes(
                                        blob_name=str(record.s3_key)
                                    )
                                except Exception:  # noqa: BLE001
                                    image_bytes = b""
                        else:
                            if s3 is None:
                                if error is None:
                                    error = (
                                        "S3 artifacts require complete GSD_S3_* config to retrieve."
                                    )
                            else:
                                try:
                                    image_bytes = s3.get_bytes(key=str(record.s3_key))
                                except Exception:  # noqa: BLE001
                                    image_bytes = b""

                        if image_bytes:
                            inline_included = True
                            image_base64 = base64.b64encode(image_bytes).decode("ascii")

                    artifact_url: str | None = None
                    artifact_url_expires_at: float | None = None
                    if include_presigned and backend != "redis":
                        try:
                            if backend == "azure":
                                if azure_client is None:
                                    raise RuntimeError("Azure blob client not configured")
                                artifact_url, artifact_url_expires_at = (
                                    azure_client.generate_sas_url(
                                        blob_name=str(record.s3_key),
                                        ttl_s=int(ttl_s),
                                    )
                                )
                            else:
                                if s3 is None:
                                    raise RuntimeError("S3 client not configured")
                                artifact_url, artifact_url_expires_at = s3.presign_get(
                                    key=str(record.s3_key), ttl_s=int(ttl_s)
                                )

                            logger.info(
                                "audit.presign_issued",
                                extra={
                                    "artifact_id": artifact_id,
                                    "tenant_id": identity.tenant_id,
                                    "subject_id": identity.subject_id,
                                    "session_id": session_id,
                                    "backend": backend,
                                    "expires_at": artifact_url_expires_at,
                                },
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "audit.presign_failed",
                                extra={
                                    "artifact_id": artifact_id,
                                    "session_id": session_id,
                                    "backend": backend,
                                },
                            )
                            artifact_url = None
                            artifact_url_expires_at = None
                            if error is None:
                                error = _truncate(
                                    f"One or more artifacts could not be presigned: {exc}",
                                    max_len=2000,
                                )

                    header_screenshots.append(
                        {
                            "id": record.artifact_id,
                            "timestamp": float(record.created_at_ms) / 1000.0,
                            "type": record.screenshot_type,
                            "session_id": record.session_id,
                            "has_error": record.has_error,
                            "mime_type": record.content_type,
                            "url": _public_url(record.page_url),
                            "step": record.step,
                            "inline_included": bool(inline_included),
                            "metadata": {},
                            "artifact": {
                                "key": record.artifact_id,
                                "url": artifact_url,
                                "content_type": record.content_type,
                                "size_bytes": record.size_bytes,
                                "created_at": float(record.created_at_ms) / 1000.0,
                                "url_expires_at": artifact_url_expires_at,
                            },
                        }
                    )
                    if inline_included and image_base64 is not None:
                        inline_images.append(
                            ImageContent(
                                type="image",
                                data=image_base64,
                                mimeType=str(record.content_type or "image/png"),
                            )
                        )

                    if len(header_screenshots) >= last_n:
                        break
        except Exception as exc:  # noqa: BLE001
            header_screenshots = []
            inline_images = []
            used_distributed = False
            if error is None:
                error = _truncate(
                    f"Distributed artifact lookup failed: {exc}",
                    max_len=2000,
                )

    legacy_screenshots: list[dict[str, Any]] = []
    if not used_distributed:
        legacy_screenshots = runtime.screenshots.get_screenshots(
            last_n=last_n,
            session_id=session_id,
            screenshot_type=screenshot_type,
            from_timestamp=from_timestamp,
            has_error=has_error,
            include_images=include_images,
        )
        for shot in legacy_screenshots:
            inline_included = bool(include_images and shot.get("image_data"))
            header_screenshots.append(
                {
                    "id": shot.get("id"),
                    "timestamp": shot.get("timestamp"),
                    "type": shot.get("type"),
                    "session_id": shot.get("session_id"),
                    "has_error": shot.get("has_error"),
                    "mime_type": shot.get("mime_type"),
                    "url": shot.get("url"),
                    "step": shot.get("step"),
                    "inline_included": inline_included,
                    "metadata": shot.get("metadata") or {},
                    "artifact": {
                        "key": shot.get("id"),
                        "url": None,
                        "content_type": str(shot.get("mime_type") or "") or None,
                        "size_bytes": None,
                        "created_at": shot.get("timestamp"),
                        "url_expires_at": None,
                    },
                }
            )

    payload = {
        "version": "gsd.get_screenshots.v1",
        "session_id": session_id,
        "filters": {
            "last_n": last_n,
            "screenshot_type": normalized_type,
            "from_timestamp": from_timestamp,
            "has_error": has_error,
            "include_images": include_images,
        },
        "screenshots": header_screenshots,
        "stats": stats,
        "error": error,
    }

    response: list[TextContent | ImageContent] = [
        TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))
    ]

    if inline_images:
        response.extend(inline_images)
    elif include_images and legacy_screenshots:
        for shot in legacy_screenshots:
            image_data = shot.get("image_data")
            if not image_data:
                continue
            response.append(
                ImageContent(
                    type="image",
                    data=image_data,
                    mimeType=str(shot.get("mime_type") or "image/png"),
                )
            )
    return response


def run_stdio() -> None:
    mcp.run(transport="stdio")
