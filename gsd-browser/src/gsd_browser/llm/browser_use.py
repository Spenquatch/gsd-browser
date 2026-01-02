"""browser-use LLM provider selection + validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..config import Settings
from .env import LLMProvider

if TYPE_CHECKING:  # pragma: no cover
    from browser_use.llm.base import BaseChatModel


def validate_llm_settings(settings: Settings) -> None:
    provider = settings.llm_provider
    model = settings.model

    if provider == "chatbrowseruse":
        if not settings.browser_use_api_key:
            raise ValueError(
                "Missing BROWSER_USE_API_KEY (required when "
                "GSD_BROWSER_LLM_PROVIDER=chatbrowseruse)."
            )
        if model not in ("bu-latest", "bu-1-0") and not model.startswith("browser-use/"):
            raise ValueError(
                "Invalid GSD_BROWSER_MODEL for chatbrowseruse; expected bu-latest, bu-1-0, "
                "or browser-use/<model>."
            )
        return

    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError(
                "Missing OPENAI_API_KEY (required when GSD_BROWSER_LLM_PROVIDER=openai)."
            )
        return

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "Missing ANTHROPIC_API_KEY (required when GSD_BROWSER_LLM_PROVIDER=anthropic)."
            )
        return

    if provider == "ollama":
        if not settings.ollama_host:
            raise ValueError("Missing OLLAMA_HOST (required when GSD_BROWSER_LLM_PROVIDER=ollama).")
        return

    raise ValueError(f"Unsupported GSD_BROWSER_LLM_PROVIDER: {provider!r}")


def create_browser_use_llm(settings: Settings) -> BaseChatModel:
    """Create the browser-use BaseChatModel for the configured provider."""
    validate_llm_settings(settings)

    try:
        import browser_use  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "browser-use is not installed. Install gsd-browser with the browser-use dependency."
        ) from exc

    provider: LLMProvider = settings.llm_provider
    if provider == "chatbrowseruse":
        return browser_use.ChatBrowserUse(
            model=settings.model,
            api_key=settings.browser_use_api_key,
            base_url=settings.browser_use_llm_url or None,
        )
    if provider == "openai":
        return browser_use.ChatOpenAI(model=settings.model, api_key=settings.openai_api_key)
    if provider == "ollama":
        return browser_use.ChatOllama(model=settings.model, host=settings.ollama_host)
    if provider == "anthropic":
        return browser_use.ChatAnthropic(model=settings.model, api_key=settings.anthropic_api_key)

    raise ValueError(f"Unsupported GSD_BROWSER_LLM_PROVIDER: {provider!r}")
