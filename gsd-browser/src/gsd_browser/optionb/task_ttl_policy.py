"""Task TTL policy enforcement for Option B.

Implements server-controlled TTL defaults and optional client override with bounds enforcement.
See FAST_MCP_V2_CANONICAL_SPEC.md §3.3 for the authoritative spec.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

# Per-tool default TTLs (seconds)
DEFAULT_TTL_WEB_EVAL_AGENT_S = 900
DEFAULT_TTL_WEB_TASK_AGENT_S = 1800
DEFAULT_TTL_WEB_TASK_AGENT_GITHUB_S = 1800

# Bounds for client-provided TTL override
DEFAULT_TTL_MIN_S = 60
DEFAULT_TTL_MAX_S = 7200


def _parse_int_env(name: str, default: int) -> int:
    """Parse an integer environment variable, returning default on missing/invalid."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _parse_bool_env(name: str, default: bool) -> bool:
    """Parse a boolean environment variable."""
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("true", "1", "yes", "on")


@dataclass(frozen=True, slots=True)
class TaskTTLConfig:
    """TTL configuration loaded from environment variables."""

    allow_client_override: bool
    min_ttl_s: int
    max_ttl_s: int
    default_web_eval_agent_s: int
    default_web_task_agent_s: int
    default_web_task_agent_github_s: int

    @classmethod
    def from_env(cls) -> TaskTTLConfig:
        """Load TTL configuration from environment variables."""
        return cls(
            allow_client_override=_parse_bool_env(
                "GSD_TASK_ALLOW_CLIENT_TTL_OVERRIDE", False
            ),
            min_ttl_s=_parse_int_env("GSD_TASK_TTL_MIN_S", DEFAULT_TTL_MIN_S),
            max_ttl_s=_parse_int_env("GSD_TASK_TTL_MAX_S", DEFAULT_TTL_MAX_S),
            default_web_eval_agent_s=_parse_int_env(
                "GSD_TASK_TTL_WEB_EVAL_AGENT_S", DEFAULT_TTL_WEB_EVAL_AGENT_S
            ),
            default_web_task_agent_s=_parse_int_env(
                "GSD_TASK_TTL_WEB_TASK_AGENT_S", DEFAULT_TTL_WEB_TASK_AGENT_S
            ),
            default_web_task_agent_github_s=_parse_int_env(
                "GSD_TASK_TTL_WEB_TASK_AGENT_GITHUB_S", DEFAULT_TTL_WEB_TASK_AGENT_GITHUB_S
            ),
        )

    def get_default_ttl_s(self, tool_name: str) -> int:
        """Get the default TTL (seconds) for a given tool."""
        if tool_name == "web_eval_agent":
            return self.default_web_eval_agent_s
        if tool_name == "web_task_agent":
            return self.default_web_task_agent_s
        if tool_name == "web_task_agent_github":
            return self.default_web_task_agent_github_s
        # Fallback for unknown tools: use web_eval_agent default
        return self.default_web_eval_agent_s


TaskToolName = Literal["web_eval_agent", "web_task_agent", "web_task_agent_github"]


class TTLOutOfBoundsError(ValueError):
    """Raised when client-provided TTL is outside allowed bounds."""

    def __init__(self, requested_s: int, min_s: int, max_s: int) -> None:
        self.requested_s = requested_s
        self.min_s = min_s
        self.max_s = max_s
        super().__init__(
            f"Client-provided TTL {requested_s}s is outside allowed bounds "
            f"[{min_s}s, {max_s}s]"
        )


def compute_effective_ttl_ms(
    *,
    tool_name: str,
    client_ttl_ms: int | None,
    config: TaskTTLConfig | None = None,
) -> int:
    """Compute the effective TTL in milliseconds for a task.

    Args:
        tool_name: The name of the tool being invoked.
        client_ttl_ms: Client-provided TTL in milliseconds (from task_meta.ttl), or None/0.
        config: TTL configuration. If None, loads from environment.

    Returns:
        Effective TTL in milliseconds.

    Raises:
        TTLOutOfBoundsError: If client override is enabled but the requested TTL is outside bounds.

    Policy:
        - If client_ttl_ms is missing/0: use server default for the tool
        - If client_ttl_ms is present:
            - If allow_client_override is False: ignore client TTL, use server default
            - If allow_client_override is True: enforce min/max bounds by rejection
    """
    if config is None:
        config = TaskTTLConfig.from_env()

    default_ttl_s = config.get_default_ttl_s(tool_name)
    default_ttl_ms = default_ttl_s * 1000

    # No client TTL provided: use server default
    if client_ttl_ms is None or client_ttl_ms <= 0:
        return default_ttl_ms

    # Client TTL provided but override not allowed: use server default
    if not config.allow_client_override:
        return default_ttl_ms

    # Client TTL provided and override allowed: enforce bounds
    client_ttl_s = client_ttl_ms // 1000
    if client_ttl_s < config.min_ttl_s or client_ttl_s > config.max_ttl_s:
        raise TTLOutOfBoundsError(
            requested_s=client_ttl_s,
            min_s=config.min_ttl_s,
            max_s=config.max_ttl_s,
        )

    return client_ttl_ms


# Module-level cached config (loaded lazily)
_cached_config: TaskTTLConfig | None = None


def get_ttl_config() -> TaskTTLConfig:
    """Get cached TTL configuration (loads from env on first call)."""
    global _cached_config
    if _cached_config is None:
        _cached_config = TaskTTLConfig.from_env()
    return _cached_config


def reset_ttl_config_cache() -> None:
    """Reset cached config (for testing)."""
    global _cached_config
    _cached_config = None
