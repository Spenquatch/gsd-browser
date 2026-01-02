"""Compatibility layer for selecting browser-use LLM providers.

The B4 tests expect a `get_browser_use_llm` helper that can be driven via explicit CLI
overrides and/or an env mapping, with provider classes patchable at module scope.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from ..config import load_settings
from .browser_use import validate_llm_settings

if TYPE_CHECKING:  # pragma: no cover
    from browser_use.llm.base import BaseChatModel


try:  # pragma: no cover
    from browser_use import ChatAnthropic as ChatAnthropic
    from browser_use import ChatBrowserUse as ChatBrowserUse
    from browser_use import ChatOllama as ChatOllama
    from browser_use import ChatOpenAI as ChatOpenAI
except Exception:  # noqa: BLE001
    ChatAnthropic = None  # type: ignore[assignment]
    ChatBrowserUse = None  # type: ignore[assignment]
    ChatOllama = None  # type: ignore[assignment]
    ChatOpenAI = None  # type: ignore[assignment]

Ollama = ChatOllama


def get_browser_use_llm(
    *,
    llm_provider: str | None,
    env: Mapping[str, str] | None,
) -> BaseChatModel:
    """Return a browser-use BaseChatModel based on CLI and/or env configuration."""
    merged = dict(env or {})
    if llm_provider is not None:
        merged["GSD_BROWSER_LLM_PROVIDER"] = llm_provider

    settings = load_settings(env=merged, strict=False)
    try:
        validate_llm_settings(settings)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    provider = settings.llm_provider
    if provider == "chatbrowseruse":
        if ChatBrowserUse is None:
            raise RuntimeError("browser-use is not importable (ChatBrowserUse missing)")
        return ChatBrowserUse(
            model=settings.model,
            api_key=settings.browser_use_api_key,
            base_url=settings.browser_use_llm_url or None,
        )
    if provider == "openai":
        if ChatOpenAI is None:
            raise RuntimeError("browser-use is not importable (ChatOpenAI missing)")
        return ChatOpenAI(model=settings.model, api_key=settings.openai_api_key)
    if provider == "ollama":
        if ChatOllama is None:
            raise RuntimeError("browser-use is not importable (ChatOllama missing)")
        return ChatOllama(model=settings.model, host=settings.ollama_host)
    if provider == "anthropic":
        if ChatAnthropic is None:
            raise RuntimeError("browser-use is not importable (ChatAnthropic missing)")
        return ChatAnthropic(model=settings.model, api_key=settings.anthropic_api_key)

    raise RuntimeError(f"Unsupported GSD_BROWSER_LLM_PROVIDER: {provider!r}")


__all__ = [
    "ChatAnthropic",
    "ChatBrowserUse",
    "ChatOllama",
    "ChatOpenAI",
    "Ollama",
    "get_browser_use_llm",
]
