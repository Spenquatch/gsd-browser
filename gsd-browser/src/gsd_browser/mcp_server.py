"""FastMCP stdio server exposing browser integration tools."""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import logging
import os
import time
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ImageContent, TextContent
from playwright.async_api import async_playwright

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
    return Path(os.path.expanduser("~/.operative/browser_state/state.json"))


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


def _get_enhanced_system_prompt(*, base_url: str) -> str | None:
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
        ensure_dashboard_running(
            settings=settings, host=DEFAULT_DASHBOARD_HOST, port=DEFAULT_DASHBOARD_PORT
        )

    dashboard_fn = getattr(runtime, "dashboard", None)
    dashboard = dashboard_fn() if callable(dashboard_fn) else None
    streaming_runtime = getattr(dashboard, "runtime", None) if dashboard else None
    control_state = getattr(streaming_runtime, "control_state", None) if streaming_runtime else None
    cdp_streamer = getattr(streaming_runtime, "cdp_streamer", None) if streaming_runtime else None
    streaming_stats = getattr(streaming_runtime, "stats", None) if streaming_runtime else None

    tool_call_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    started = datetime.now(UTC).timestamp()
    normalized_url = _normalize_url(url)

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
            "mode": str(mode) if mode is not None else None,
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
            "mode": str(mode) if mode is not None else None,
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

    state_path = _browser_state_path()
    storage_state: str | None = str(state_path) if state_path.exists() else None
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
            record(
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
            record(
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
        llms = create_browser_use_llms(settings)
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

        cdp_attached = False

        async def attach_streaming_when_ready() -> None:
            nonlocal streaming_disabled_reason
            if cdp_streamer is None:
                return
            if getattr(streaming_stats, "streaming_mode", None) != "cdp":
                return

            started_wait = time.time()
            while True:
                if not hasattr(browser_session, "cdp_client"):
                    return
                if getattr(browser_session, "cdp_client", None) is not None:
                    break
                if time.time() - started_wait > 10.0:
                    streaming_disabled_reason = "cdp_not_ready"
                    note_detached = getattr(streaming_stats, "note_cdp_detached", None)
                    if callable(note_detached):
                        note_detached(error=streaming_disabled_reason)
                    return
                await asyncio.sleep(0.05)

            try:
                start_browser_use = getattr(cdp_streamer, "start_browser_use", None)
                if not callable(start_browser_use):
                    raise RuntimeError("cdp_streamer.start_browser_use unavailable")
                await start_browser_use(browser_session=browser_session, session_id=session_id)
            except Exception as exc:  # noqa: BLE001
                streaming_disabled_reason = _truncate(f"{type(exc).__name__}: {exc}", max_len=400)
                note_detached = getattr(streaming_stats, "note_cdp_detached", None)
                if callable(note_detached):
                    note_detached(error=streaming_disabled_reason)

        async def attach_cdp_when_ready() -> None:
            nonlocal cdp_attached
            while True:
                cdp_client = getattr(browser_session, "cdp_client", None)
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
            enhanced_prompt = _get_enhanced_system_prompt(base_url=normalized_url)
            use_override_mode = enhanced_prompt is not None

            if use_override_mode:
                logger.info(
                    "using_enhanced_system_prompt",
                    extra={"session_id": session_id, "prompt_length": len(enhanced_prompt)},
                )

            # Prepare agent configuration
            prompt_wrapper = _browser_use_prompt_wrapper(base_url=normalized_url)

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
            if steps >= effective_max_steps:
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
        payload = {
            "version": "gsd.web_eval_agent.v1",
            "session_id": session_id,
            "tool_call_id": tool_call_id,
            "url": normalized_url,
            "task": task,
            "mode": selected_mode,
            "status": status,
            "result": result,
            "summary": summary,
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

        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
    except TimeoutError:
        duration_s = max(0.0, datetime.now(UTC).timestamp() - started)
        warnings = _dedupe([*warnings, f"timed_out_after_s={effective_budget_s:g}"])[:20]

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
            "status": "failed",
            "result": None,
            "summary": _truncate(
                f"Timeout: tool budget exceeded (budget_s={effective_budget_s:g}).",
                max_len=2000,
            ),
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
                "Increase budget_s (or reduce task scope) and retry.",
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

        payload = {
            "version": "gsd.web_eval_agent.v1",
            "session_id": session_id,
            "tool_call_id": tool_call_id,
            "url": normalized_url,
            "task": task,
            "mode": selected_mode,
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
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]


@mcp.tool(name="get_run_events")
async def get_run_events(
    session_id: str | None = None,
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
        session_id: Filter to a single session_id (optional).
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

    get_events = getattr(run_events, "get_events", None) if run_events is not None else None
    events: list[dict[str, Any]]
    if error is None and callable(get_events):
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
        "events": events,
        "stats": {
            "counts": counts,
            "oldest_timestamp": min(timestamps) if timestamps else None,
            "newest_timestamp": max(timestamps) if timestamps else None,
        },
        "error": error,
    }

    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]


@mcp.tool(name="setup_browser_state")
async def setup_browser_state(
    url: str | None = None, ctx: Context | None = None
) -> list[TextContent]:
    """Sets up and saves browser state for future use.

    This tool should only be called in one scenario:
    1. The user explicitly requests to set up browser state/authentication

    Launches a non-headless browser for user interaction, allows login/authentication,
    and saves the browser state (cookies, local storage, etc.) to a local file.

    Args:
        url: Optional URL to navigate to upon opening the browser.
        ctx: The MCP context (used for progress reporting, not directly here).

    Returns:
        list[TextContent]: Confirmation of state saving or error messages.
    """
    _ = ctx
    runtime = get_runtime()
    settings = load_settings(strict=False)
    runtime.ensure_dashboard_running(
        settings=settings, host=DEFAULT_DASHBOARD_HOST, port=DEFAULT_DASHBOARD_PORT
    )

    tool_call_id = str(uuid.uuid4())
    normalized_url = _normalize_url(url) if url else None
    state_path = _browser_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "setup_browser_state called",
        extra={"tool_call_id": tool_call_id, "url": normalized_url, "state_path": str(state_path)},
    )

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            if normalized_url:
                await page.goto(normalized_url, wait_until="domcontentloaded")

            await page.wait_for_event("close")

            await context.storage_state(path=str(state_path))
            await context.close()
            await browser.close()

        return [
            TextContent(
                type="text",
                text=(
                    "Saved browser state.\n"
                    f"- path: {state_path}\n"
                    "Use setup_browser_state(url=...) to refresh it if the session expires."
                ),
            ),
        ]
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        return [
            TextContent(
                type="text",
                text=f"Error executing setup_browser_state: {exc}\n\nTraceback:\n{tb}",
            )
        ]


@mcp.tool(name="get_screenshots")
async def get_screenshots(
    last_n: int = 5,
    screenshot_type: str = "agent_step",
    session_id: str | None = None,
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
        session_id: Filter by specific session
        from_timestamp: Only get screenshots after this time
        has_error: Filter for error screenshots only
        include_images: If False, return metadata only

    Returns:
        Screenshot data or metadata with debugging information
    """
    _ = ctx
    runtime = get_runtime()
    last_n = min(max(last_n, 0), 20)

    screenshots = runtime.screenshots.get_screenshots(
        last_n=last_n,
        session_id=session_id,
        screenshot_type=screenshot_type,
        from_timestamp=from_timestamp,
        has_error=has_error,
        include_images=include_images,
    )
    stats = runtime.screenshots.get_stats()

    response: list[TextContent | ImageContent] = [
        TextContent(
            type="text",
            text=(
                f"Retrieved {len(screenshots)} screenshots from storage "
                f"(Total stored: {stats['total_screenshots']}, Sampling: {stats['sampling_rate']})"
            ),
        )
    ]

    if include_images:
        for shot in screenshots:
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

    if screenshots:
        lines: list[str] = []
        for shot in screenshots:
            prefix = f"[{shot.get('type', 'unknown')}] "
            step = shot.get("step")
            if step is not None:
                prefix += f"Step {step} | "
            url_value = str(shot.get("url") or "N/A")
            ts = shot.get("timestamp")
            time_value = "N/A"
            if isinstance(ts, (int, float)):
                time_value = datetime.fromtimestamp(ts, UTC).isoformat()
            err = " | ERROR" if shot.get("has_error") else ""
            lines.append(f"{prefix}URL: {url_value} | Time: {time_value}{err}")

        response.append(TextContent(type="text", text="\n".join(lines)))

    return response


def run_stdio() -> None:
    mcp.run(transport="stdio")
