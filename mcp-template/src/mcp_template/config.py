"""Configuration loader for the MCP template."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .streaming.env import (
    StreamingMode,
    StreamingQuality,
    normalize_streaming_mode,
    normalize_streaming_quality,
)


class Settings(BaseModel):
    """User configuration driven by environment variables or .env files."""

    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    model: str = Field("claude-haiku-4-5", alias="MCP_TEMPLATE_MODEL")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    json_logs: bool = Field(False, alias="MCP_TEMPLATE_JSON_LOGS")
    streaming_mode: StreamingMode = Field("cdp", alias="STREAMING_MODE")
    streaming_quality: StreamingQuality = Field("med", alias="STREAMING_QUALITY")

    model_config = ConfigDict(populate_by_name=True)

    def to_mcp_snippet(self) -> str:
        """Return JSON snippet for MCP configuration."""
        snippet = {
            "mcpServers": {
                "mcp-template": {
                    "type": "stdio",
                    "command": "mcp-template",
                    "env": {"ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}"},
                    "description": "Reusable MCP template server",
                }
            }
        }
        return json.dumps(snippet, indent=2)

    def to_mcp_toml(self) -> str:
        """Return TOML snippet for MCP configuration."""
        return (
            "[mcp_servers.mcp-template]\n"
            'command = "mcp-template"\n'
            'env = { ANTHROPIC_API_KEY = "${ANTHROPIC_API_KEY}" }\n'
            'description = "Reusable MCP template server"\n'
        )


def _build_env_mapping(env: Mapping[str, str] | None = None) -> dict[str, str]:
    src = dict(os.environ)
    if env:
        src.update(env)
    return src


def load_settings(
    *, env: Mapping[str, str] | None = None, env_file: str | None = ".env", strict: bool = False
) -> Settings:
    """Load settings by merging .env (if present) and environment variables."""
    if env_file:
        env_path = Path(env_file)
        if env_path.exists():
            load_dotenv(env_path, override=False)

    merged = _build_env_mapping(env)
    anthropic_api_key = merged.get("ANTHROPIC_API_KEY")
    if not anthropic_api_key and not strict:
        anthropic_api_key = ""
    streaming_mode = normalize_streaming_mode(merged.get("STREAMING_MODE"))
    streaming_quality = normalize_streaming_quality(merged.get("STREAMING_QUALITY"))
    try:
        payload: dict[str, object] = {
            "ANTHROPIC_API_KEY": anthropic_api_key,
            "STREAMING_MODE": streaming_mode,
            "STREAMING_QUALITY": streaming_quality,
        }
        if merged.get("MCP_TEMPLATE_MODEL") is not None:
            payload["MCP_TEMPLATE_MODEL"] = merged["MCP_TEMPLATE_MODEL"]
        if merged.get("LOG_LEVEL") is not None:
            payload["LOG_LEVEL"] = merged["LOG_LEVEL"]
        if merged.get("MCP_TEMPLATE_JSON_LOGS") is not None:
            payload["MCP_TEMPLATE_JSON_LOGS"] = merged["MCP_TEMPLATE_JSON_LOGS"]

        return Settings.model_validate(payload, strict=strict)
    except ValidationError as exc:
        raise RuntimeError(f"Invalid MCP template configuration: {exc}") from exc


__all__ = ["Settings", "load_settings"]
