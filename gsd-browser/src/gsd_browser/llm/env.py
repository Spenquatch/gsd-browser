"""Environment helpers for selecting LLM providers."""

from __future__ import annotations

from typing import Literal, cast

LLMProvider = Literal["anthropic", "chatbrowseruse", "openai", "ollama"]


def normalize_llm_provider(value: str | None) -> LLMProvider:
    if not value:
        return "anthropic"

    normalized = value.strip().lower()
    normalized = {
        "browser-use": "chatbrowseruse",
        "browser_use": "chatbrowseruse",
        "browseruse": "chatbrowseruse",
        "chat-browser-use": "chatbrowseruse",
    }.get(normalized, normalized)

    if normalized in ("anthropic", "chatbrowseruse", "openai", "ollama"):
        return cast(LLMProvider, normalized)
    return "anthropic"
