"""Configuration loader for the GSD Browser MCP server."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .llm.env import LLMProvider, normalize_llm_provider
from .streaming.env import (
    StreamingMode,
    StreamingQuality,
    normalize_streaming_mode,
    normalize_streaming_quality,
)
from .user_config import default_env_path


class Settings(BaseModel):
    """User configuration driven by environment variables or .env files."""

    llm_provider: LLMProvider = Field("anthropic", alias="GSD_BROWSER_LLM_PROVIDER")

    # Model selection
    # DEFAULT: claude-haiku-4-5 with Sonnet fallback (cost-optimized with reliability safety net)
    # Alternative: claude-sonnet-4-5 (100% pass rate, higher cost, no fallback needed)
    # Override via GSD_BROWSER_MODEL environment variable or .env file
    # See .env.example and artifacts/real_world_sanity/MODEL_COMPARISON_haiku_vs_sonnet.md
    model: str = Field("claude-haiku-4-5", alias="GSD_BROWSER_MODEL")

    fallback_llm_provider: LLMProvider | None = Field(
        "anthropic", alias="GSD_BROWSER_FALLBACK_LLM_PROVIDER"
    )
    fallback_model: str = Field("claude-sonnet-4-5", alias="GSD_BROWSER_FALLBACK_MODEL")

    openai_add_schema_to_system_prompt: bool = Field(
        True, alias="GSD_BROWSER_OPENAI_ADD_SCHEMA_TO_SYSTEM_PROMPT"
    )
    openai_dont_force_structured_output: bool = Field(
        False, alias="GSD_BROWSER_OPENAI_DONT_FORCE_STRUCTURED_OUTPUT"
    )

    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    browser_use_api_key: str = Field("", alias="BROWSER_USE_API_KEY")
    browser_use_llm_url: str = Field("", alias="BROWSER_USE_LLM_URL")
    ollama_host: str = Field("http://localhost:11434", alias="OLLAMA_HOST")
    browser_executable_path: str = Field("", alias="GSD_BROWSER_BROWSER_EXECUTABLE_PATH")

    # MCP tool exposure controls
    # - If enabled_tools is set, only those tools are advertised (allowlist).
    # - If disabled_tools is set, those tools are removed from the advertised set (denylist).
    # - If enabled_tools is unset/empty, all tools are enabled by default.
    mcp_enabled_tools: str = Field("", alias="GSD_BROWSER_MCP_ENABLED_TOOLS")
    mcp_disabled_tools: str = Field("", alias="GSD_BROWSER_MCP_DISABLED_TOOLS")

    log_level: str = Field("INFO", alias="LOG_LEVEL")
    json_logs: bool = Field(False, alias="GSD_BROWSER_JSON_LOGS")
    streaming_mode: StreamingMode = Field("cdp", alias="STREAMING_MODE")
    streaming_quality: StreamingQuality = Field("med", alias="STREAMING_QUALITY")

    # Web evaluation timeouts
    # NOTE: Defaults optimized for claude-haiku-4-5 with Sonnet fallback
    # Budget is set generously (240s) since max_steps (25) is the real safety limit
    # If task completes in 30s, budget of 240s doesn't matter - set generously
    # See .env.example and artifacts/real_world_sanity/MODEL_COMPARISON_haiku_vs_sonnet.md
    web_eval_budget_s: float = Field(240.0, alias="GSD_BROWSER_WEB_EVAL_BUDGET_S")
    web_eval_max_steps: int = Field(25, alias="GSD_BROWSER_WEB_EVAL_MAX_STEPS")
    web_eval_step_timeout_s: float = Field(15.0, alias="GSD_BROWSER_WEB_EVAL_STEP_TIMEOUT_S")

    # Vision mode configuration
    # Controls how browser-use perceives web pages (DOM-only, vision-only, or hybrid)
    # Options:
    #   - "auto": Intelligent hybrid (includes screenshot tool, only uses when model requests)
    #   - "true": Always use vision (hybrid DOM+Vision, most reliable but expensive)
    #   - "false": DOM-only (no screenshots, fastest and cheapest)
    # RECOMMENDED: "auto" for balanced cost and capability
    use_vision: str = Field("auto", alias="GSD_BROWSER_USE_VISION")

    auto_pause_on_take_control: bool = Field(True, alias="GSD_BROWSER_AUTO_PAUSE_ON_TAKE_CONTROL")

    model_config = ConfigDict(populate_by_name=True)

    def _mcp_env(self, *, include_key_placeholders: bool = False) -> dict[str, str]:
        """Environment variables to configure the MCP server process.

        Default behavior: point at a stable per-user env file so MCP hosts don't
        depend on cwd or `${VAR}` interpolation support.
        """

        if not include_key_placeholders:
            return {"GSD_BROWSER_ENV_FILE": str(default_env_path())}

        env: dict[str, str] = {
            "GSD_BROWSER_LLM_PROVIDER": self.llm_provider,
            "GSD_BROWSER_MODEL": self.model,
        }

        if self.llm_provider == "ollama":
            env["OLLAMA_HOST"] = self.ollama_host
        elif self.llm_provider == "openai":
            env["OPENAI_API_KEY"] = "${OPENAI_API_KEY}"
        elif self.llm_provider == "chatbrowseruse":
            env["BROWSER_USE_API_KEY"] = "${BROWSER_USE_API_KEY}"
            if self.browser_use_llm_url:
                env["BROWSER_USE_LLM_URL"] = self.browser_use_llm_url
        else:
            # Anthropic (default)
            env["ANTHROPIC_API_KEY"] = "${ANTHROPIC_API_KEY}"

            # Include fallback configuration if set
            if self.fallback_llm_provider:
                env["GSD_BROWSER_FALLBACK_LLM_PROVIDER"] = str(self.fallback_llm_provider)
            if self.fallback_model:
                env["GSD_BROWSER_FALLBACK_MODEL"] = self.fallback_model

        return env

    def to_mcp_snippet(self, *, include_key_placeholders: bool = False) -> str:
        """Return JSON snippet for MCP configuration."""
        snippet = {
            "mcpServers": {
                "gsd-browser": {
                    "type": "stdio",
                    "command": "gsd",
                    "args": ["mcp", "serve"],
                    "env": self._mcp_env(include_key_placeholders=include_key_placeholders),
                    "description": "GSD Browser MCP server",
                }
            }
        }
        return json.dumps(snippet, indent=2)

    def to_mcp_toml(self, *, include_key_placeholders: bool = False) -> str:
        """Return TOML snippet for MCP configuration."""
        env = self._mcp_env(include_key_placeholders=include_key_placeholders)
        env_lines = "\n".join(f'{key} = "{value}"' for key, value in env.items())
        return (
            "[mcp_servers.gsd-browser]\n"
            'command = "gsd"\n'
            'args = ["mcp", "serve"]\n'
            'description = "GSD Browser MCP server"\n'
            "\n"
            "[mcp_servers.gsd-browser.env]\n"
            f"{env_lines}\n"
        )


def _build_env_mapping(env: Mapping[str, str] | None = None) -> dict[str, str]:
    src = dict(os.environ)
    if env:
        src.update(env)
    return src


def load_settings(
    *,
    env: Mapping[str, str] | None = None,
    env_file: str | None = ".env",
    strict: bool = False,
) -> Settings:
    """Load settings by merging .env (if present) and environment variables."""
    selected_env_file = env_file
    # Allow overriding the default ".env" location (useful when the server is launched from a
    # different working directory, e.g. from an MCP host like Claude).
    if env_file == ".env":
        override_env_file = None
        if env and env.get("GSD_BROWSER_ENV_FILE"):
            override_env_file = env.get("GSD_BROWSER_ENV_FILE")
        elif os.environ.get("GSD_BROWSER_ENV_FILE"):
            override_env_file = os.environ.get("GSD_BROWSER_ENV_FILE")
        if override_env_file:
            selected_env_file = override_env_file

    if selected_env_file:
        env_path = Path(selected_env_file).expanduser()
        if env_path.exists():
            load_dotenv(env_path, override=False)
        elif selected_env_file == ".env" and not (env and env.get("GSD_BROWSER_ENV_FILE")):
            # Production default: also look for a stable per-user config file so a
            # pipx-installed CLI works from any directory without extra env vars.
            user_env_path = default_env_path()
            if user_env_path.exists():
                load_dotenv(user_env_path, override=False)

    merged = _build_env_mapping(env)
    llm_provider = normalize_llm_provider(merged.get("GSD_BROWSER_LLM_PROVIDER"))
    fallback_llm_provider_raw = merged.get("GSD_BROWSER_FALLBACK_LLM_PROVIDER")
    fallback_llm_provider = (
        normalize_llm_provider(fallback_llm_provider_raw) if fallback_llm_provider_raw else None
    )
    streaming_mode = normalize_streaming_mode(merged.get("STREAMING_MODE"))
    streaming_quality = normalize_streaming_quality(merged.get("STREAMING_QUALITY"))
    try:
        payload: dict[str, object] = {
            "GSD_BROWSER_LLM_PROVIDER": llm_provider,
            "STREAMING_MODE": streaming_mode,
            "STREAMING_QUALITY": streaming_quality,
        }
        # Only include fallback provider if explicitly set in environment
        # (otherwise Pydantic Field default will be used)
        if fallback_llm_provider is not None:
            payload["GSD_BROWSER_FALLBACK_LLM_PROVIDER"] = fallback_llm_provider
        if merged.get("ANTHROPIC_API_KEY") is not None:
            payload["ANTHROPIC_API_KEY"] = merged["ANTHROPIC_API_KEY"]
        if merged.get("OPENAI_API_KEY") is not None:
            payload["OPENAI_API_KEY"] = merged["OPENAI_API_KEY"]
        if merged.get("BROWSER_USE_API_KEY") is not None:
            payload["BROWSER_USE_API_KEY"] = merged["BROWSER_USE_API_KEY"]
        if merged.get("BROWSER_USE_LLM_URL") is not None:
            payload["BROWSER_USE_LLM_URL"] = merged["BROWSER_USE_LLM_URL"]
        if merged.get("OLLAMA_HOST") is not None:
            payload["OLLAMA_HOST"] = merged["OLLAMA_HOST"]
        if merged.get("GSD_BROWSER_BROWSER_EXECUTABLE_PATH") is not None:
            payload["GSD_BROWSER_BROWSER_EXECUTABLE_PATH"] = merged[
                "GSD_BROWSER_BROWSER_EXECUTABLE_PATH"
            ]
        if merged.get("GSD_BROWSER_MCP_ENABLED_TOOLS") is not None:
            payload["GSD_BROWSER_MCP_ENABLED_TOOLS"] = merged["GSD_BROWSER_MCP_ENABLED_TOOLS"]
        if merged.get("GSD_BROWSER_MCP_DISABLED_TOOLS") is not None:
            payload["GSD_BROWSER_MCP_DISABLED_TOOLS"] = merged["GSD_BROWSER_MCP_DISABLED_TOOLS"]

        model_value = merged.get("GSD_BROWSER_MODEL")
        model_value = model_value.strip() if isinstance(model_value, str) else None
        if model_value:
            payload["GSD_BROWSER_MODEL"] = model_value
        elif llm_provider == "chatbrowseruse":
            payload["GSD_BROWSER_MODEL"] = "bu-latest"
        elif llm_provider == "openai":
            payload["GSD_BROWSER_MODEL"] = "gpt-4o-mini"
        elif llm_provider == "ollama":
            payload["GSD_BROWSER_MODEL"] = "llama3.2"

        if merged.get("GSD_BROWSER_FALLBACK_MODEL") is not None:
            payload["GSD_BROWSER_FALLBACK_MODEL"] = merged["GSD_BROWSER_FALLBACK_MODEL"]
        if merged.get("GSD_BROWSER_OPENAI_ADD_SCHEMA_TO_SYSTEM_PROMPT") is not None:
            payload["GSD_BROWSER_OPENAI_ADD_SCHEMA_TO_SYSTEM_PROMPT"] = merged[
                "GSD_BROWSER_OPENAI_ADD_SCHEMA_TO_SYSTEM_PROMPT"
            ]
        if merged.get("GSD_BROWSER_OPENAI_DONT_FORCE_STRUCTURED_OUTPUT") is not None:
            payload["GSD_BROWSER_OPENAI_DONT_FORCE_STRUCTURED_OUTPUT"] = merged[
                "GSD_BROWSER_OPENAI_DONT_FORCE_STRUCTURED_OUTPUT"
            ]
        if merged.get("LOG_LEVEL") is not None:
            payload["LOG_LEVEL"] = merged["LOG_LEVEL"]
        if merged.get("GSD_BROWSER_JSON_LOGS") is not None:
            payload["GSD_BROWSER_JSON_LOGS"] = merged["GSD_BROWSER_JSON_LOGS"]
        if merged.get("GSD_BROWSER_WEB_EVAL_BUDGET_S") is not None:
            payload["GSD_BROWSER_WEB_EVAL_BUDGET_S"] = merged["GSD_BROWSER_WEB_EVAL_BUDGET_S"]
        if merged.get("GSD_BROWSER_WEB_EVAL_MAX_STEPS") is not None:
            payload["GSD_BROWSER_WEB_EVAL_MAX_STEPS"] = merged["GSD_BROWSER_WEB_EVAL_MAX_STEPS"]
        if merged.get("GSD_BROWSER_WEB_EVAL_STEP_TIMEOUT_S") is not None:
            payload["GSD_BROWSER_WEB_EVAL_STEP_TIMEOUT_S"] = merged[
                "GSD_BROWSER_WEB_EVAL_STEP_TIMEOUT_S"
            ]
        if merged.get("GSD_BROWSER_USE_VISION") is not None:
            payload["GSD_BROWSER_USE_VISION"] = merged["GSD_BROWSER_USE_VISION"]
        if merged.get("GSD_BROWSER_AUTO_PAUSE_ON_TAKE_CONTROL") is not None:
            payload["GSD_BROWSER_AUTO_PAUSE_ON_TAKE_CONTROL"] = merged[
                "GSD_BROWSER_AUTO_PAUSE_ON_TAKE_CONTROL"
            ]

        return Settings.model_validate(payload, strict=strict)
    except ValidationError as exc:
        raise RuntimeError(f"Invalid gsd-browser configuration: {exc}") from exc


__all__ = ["Settings", "load_settings"]
