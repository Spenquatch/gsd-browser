"""Configuration loader for the MCP template."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Settings(BaseModel):
    """User configuration driven by environment variables or .env files."""

    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    model: str = Field("claude-haiku-4-5", alias="MCP_TEMPLATE_MODEL")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    json_logs: bool = Field(False, alias="MCP_TEMPLATE_JSON_LOGS")

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
    *, env: Mapping[str, str] | None = None, env_file: str | None = ".env", strict: bool = True
) -> Settings:
    """Load settings by merging .env (if present) and environment variables."""
    if env_file:
        env_path = Path(env_file)
        if env_path.exists():
            load_dotenv(env_path, override=False)

    merged = _build_env_mapping(env)
    try:
        return Settings.model_validate(
            {
                "ANTHROPIC_API_KEY": merged.get("ANTHROPIC_API_KEY"),
                "MCP_TEMPLATE_MODEL": merged.get("MCP_TEMPLATE_MODEL"),
                "LOG_LEVEL": merged.get("LOG_LEVEL"),
                "MCP_TEMPLATE_JSON_LOGS": merged.get("MCP_TEMPLATE_JSON_LOGS"),
            },
            strict=strict,
        )
    except ValidationError as exc:
        raise RuntimeError(f"Invalid MCP template configuration: {exc}") from exc


__all__ = ["Settings", "load_settings"]
