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


class Settings(BaseModel):
    """User configuration driven by environment variables or .env files."""

    llm_provider: LLMProvider = Field("anthropic", alias="GSD_BROWSER_LLM_PROVIDER")
    model: str = Field("claude-haiku-4-5", alias="GSD_BROWSER_MODEL")

    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    browser_use_api_key: str = Field("", alias="BROWSER_USE_API_KEY")
    browser_use_llm_url: str = Field("", alias="BROWSER_USE_LLM_URL")
    ollama_host: str = Field("http://localhost:11434", alias="OLLAMA_HOST")

    log_level: str = Field("INFO", alias="LOG_LEVEL")
    json_logs: bool = Field(False, alias="GSD_BROWSER_JSON_LOGS")
    streaming_mode: StreamingMode = Field("cdp", alias="STREAMING_MODE")
    streaming_quality: StreamingQuality = Field("med", alias="STREAMING_QUALITY")

    model_config = ConfigDict(populate_by_name=True)

    def _mcp_env(self) -> dict[str, str]:
        env: dict[str, str] = {
            "GSD_BROWSER_LLM_PROVIDER": "${GSD_BROWSER_LLM_PROVIDER}",
            "GSD_BROWSER_MODEL": "${GSD_BROWSER_MODEL}",
        }

        if self.llm_provider == "ollama":
            env["OLLAMA_HOST"] = "${OLLAMA_HOST}"
        elif self.llm_provider == "openai":
            env["OPENAI_API_KEY"] = "${OPENAI_API_KEY}"
        elif self.llm_provider == "chatbrowseruse":
            env["BROWSER_USE_API_KEY"] = "${BROWSER_USE_API_KEY}"
        else:
            env["ANTHROPIC_API_KEY"] = "${ANTHROPIC_API_KEY}"

        return env

    def to_mcp_snippet(self) -> str:
        """Return JSON snippet for MCP configuration."""
        snippet = {
            "mcpServers": {
                "gsd-browser": {
                    "type": "stdio",
                    "command": "gsd-browser",
                    "env": self._mcp_env(),
                    "description": "GSD Browser MCP server",
                }
            }
        }
        return json.dumps(snippet, indent=2)

    def to_mcp_toml(self) -> str:
        """Return TOML snippet for MCP configuration."""
        env_items = ", ".join(f'{key} = "{value}"' for key, value in self._mcp_env().items())
        return (
            "[mcp_servers.gsd-browser]\n"
            'command = "gsd-browser"\n'
            f"env = {{ {env_items} }}\n"
            'description = "GSD Browser MCP server"\n'
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
    if env_file:
        env_path = Path(env_file)
        if env_path.exists():
            load_dotenv(env_path, override=False)

    merged = _build_env_mapping(env)
    llm_provider = normalize_llm_provider(merged.get("GSD_BROWSER_LLM_PROVIDER"))
    streaming_mode = normalize_streaming_mode(merged.get("STREAMING_MODE"))
    streaming_quality = normalize_streaming_quality(merged.get("STREAMING_QUALITY"))
    try:
        payload: dict[str, object] = {
            "GSD_BROWSER_LLM_PROVIDER": llm_provider,
            "STREAMING_MODE": streaming_mode,
            "STREAMING_QUALITY": streaming_quality,
        }
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
        if merged.get("GSD_BROWSER_MODEL") is not None:
            payload["GSD_BROWSER_MODEL"] = merged["GSD_BROWSER_MODEL"]
        if merged.get("LOG_LEVEL") is not None:
            payload["LOG_LEVEL"] = merged["LOG_LEVEL"]
        if merged.get("GSD_BROWSER_JSON_LOGS") is not None:
            payload["GSD_BROWSER_JSON_LOGS"] = merged["GSD_BROWSER_JSON_LOGS"]

        return Settings.model_validate(payload, strict=strict)
    except ValidationError as exc:
        raise RuntimeError(f"Invalid gsd-browser configuration: {exc}") from exc


__all__ = ["Settings", "load_settings"]
