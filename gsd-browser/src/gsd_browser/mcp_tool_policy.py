"""MCP tool exposure controls.

MCP servers advertise a static set of tools to the client via `list_tools`. For ops/security
and UX reasons, we support restricting which tools are advertised based on environment/config.

This module is intentionally pure (parse/compute) with a small `apply_*` helper to mutate a
FastMCP instance by removing tools before the server starts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("gsd_browser.mcp_tools")

# Keep this list explicit so `list-tools` works without importing the server runtime.
# Update alongside tool definitions in `mcp_server.py`.
KNOWN_MCP_TOOLS: tuple[str, ...] = (
    "web_eval_agent",
    "web_task_agent",
    "web_task_agent_github",
    "get_run_events",
    "setup_browser_state",
    "get_screenshots",
)


def normalize_tool_name(name: str) -> str:
    return str(name).strip().lower().replace("-", "_")


def _split_tokens(value: str) -> list[str]:
    raw = str(value)
    tokens: list[str] = []
    for part in raw.replace("\n", ",").split(","):
        token = part.strip()
        if token:
            tokens.append(token)
    return tokens


def parse_tool_selector(value: str | None) -> tuple[str | None, set[str]]:
    """Parse a selector string into a mode and tool names.

    Returns:
      (mode, names)
        - mode: None (unset), "all", or "none"
        - names: normalized tool names (may include unknown names; caller decides)

    Examples:
      None / "" -> (None, set())
      "*" / "all" -> ("all", set())
      "none" -> ("none", set())
      "a,b" -> (None, {"a","b"})
    """

    if value is None:
        return None, set()
    text = str(value).strip()
    if not text:
        return None, set()

    lowered = text.strip().lower()
    if lowered in {"*", "all"}:
        return "all", set()
    if lowered in {"none"}:
        return "none", set()

    tokens = _split_tokens(text)
    return None, {normalize_tool_name(token) for token in tokens}


@dataclass(frozen=True)
class ToolExposurePolicy:
    known_tools: set[str]
    enabled_tools: set[str]
    disabled_tools: set[str]
    unknown_requested: set[str]

    @property
    def advertised_tools(self) -> set[str]:
        return self.enabled_tools - self.disabled_tools


def compute_tool_exposure_policy(
    *,
    known_tools: set[str],
    enabled_raw: str | None,
    disabled_raw: str | None,
) -> ToolExposurePolicy:
    enabled_mode, enabled_names = parse_tool_selector(enabled_raw)
    _disabled_mode, disabled_names = parse_tool_selector(disabled_raw)

    unknown_requested = (enabled_names | disabled_names) - known_tools

    if enabled_mode == "none":
        enabled_tools = set()
    elif enabled_mode == "all":
        enabled_tools = set(known_tools)
    elif enabled_raw is not None and str(enabled_raw).strip():
        enabled_tools = enabled_names & known_tools
    else:
        enabled_tools = set(known_tools)

    disabled_tools = disabled_names & known_tools

    return ToolExposurePolicy(
        known_tools=set(known_tools),
        enabled_tools=enabled_tools,
        disabled_tools=disabled_tools,
        unknown_requested=unknown_requested,
    )


def apply_tool_exposure_policy(*, mcp: FastMCP, policy: ToolExposurePolicy) -> None:
    """Remove tools from a FastMCP instance to match the advertised tool set.

    Must be called before `mcp.run(...)` so clients receive a consistent list.
    """

    advertised = policy.advertised_tools
    for name in sorted(policy.known_tools):
        if name in advertised:
            continue
        try:
            mcp.remove_tool(name)
        except Exception:  # noqa: BLE001
            # If the tool isn't registered (or already removed), keep going.
            logger.debug("remove_tool_failed", extra={"tool": name}, exc_info=True)
