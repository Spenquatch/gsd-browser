"""browser-use LLM provider selection + validation."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..config import Settings
from .env import LLMProvider

if TYPE_CHECKING:  # pragma: no cover
    from browser_use.llm.base import BaseChatModel


def _provider_timeout_kwargs(
    provider: type[object], timeout_s: float | None
) -> dict[str, float] | None:
    if timeout_s is None:
        return None
    try:
        signature = inspect.signature(provider)
    except (TypeError, ValueError):
        return None

    timeout_value = float(timeout_s)
    for param_name in ("timeout", "request_timeout", "timeout_s"):
        if param_name in signature.parameters:
            return {param_name: timeout_value}
    return None


def validate_llm_settings(settings: Settings) -> None:
    provider = settings.llm_provider
    model = settings.model
    model_lower = model.strip().lower()
    if not model_lower:
        raise ValueError(
            "Missing GSD_MODEL. Set a provider-specific model name (example: "
            "claude-haiku-4-5, gpt-4o-mini, bu-latest, llama3.2)."
        )

    if provider == "chatbrowseruse":
        if not settings.browser_use_api_key:
            raise ValueError(
                "Missing BROWSER_USE_API_KEY (required when "
                "GSD_LLM_PROVIDER=chatbrowseruse)."
            )
        if model not in ("bu-latest", "bu-1-0") and not model.startswith("browser-use/"):
            raise ValueError(
                "Invalid GSD_MODEL for chatbrowseruse; expected bu-latest, bu-1-0, "
                "or browser-use/<model>."
            )
        return

    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError(
                "Missing OPENAI_API_KEY (required when GSD_LLM_PROVIDER=openai)."
            )
        if model_lower.startswith(("claude-", "bu-", "browser-use/")):
            raise ValueError(
                "GSD_MODEL looks incompatible with GSD_LLM_PROVIDER=openai. "
                "Set an OpenAI model (recommended: gpt-4o-mini) or switch providers."
            )

        supports_json_schema = model_lower.startswith(
            (
                "gpt-4o",
                "chatgpt-4o",
                "gpt-4.1",
                "gpt-5",
                "o1",
                "o3",
                "o4",
                "codex-mini",
            )
        )
        if not supports_json_schema and not settings.openai_dont_force_structured_output:
            raise ValueError(
                "OpenAI provider requires a model that supports JSON schema structured output "
                "for browser-use actions. Set GSD_MODEL to a modern model "
                "(recommended: gpt-4o-mini) or opt into unforced structured output by setting "
                "GSD_OPENAI_DONT_FORCE_STRUCTURED_OUTPUT=true "
                "(may increase AgentOutput validation failures)."
            )
        return

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "Missing ANTHROPIC_API_KEY (required when GSD_LLM_PROVIDER=anthropic)."
            )
        if model_lower.startswith(("gpt-", "o1", "o3", "o4", "bu-", "browser-use/")):
            raise ValueError(
                "GSD_MODEL looks incompatible with GSD_LLM_PROVIDER=anthropic. "
                "Set a Claude model (recommended: claude-haiku-4-5) or switch providers."
            )
        return

    if provider == "ollama":
        if not settings.ollama_host:
            raise ValueError("Missing OLLAMA_HOST (required when GSD_LLM_PROVIDER=ollama).")
        if model_lower.startswith(("gpt-", "o1", "o3", "o4", "claude-", "bu-", "browser-use/")):
            raise ValueError(
                "GSD_MODEL looks incompatible with GSD_LLM_PROVIDER=ollama. "
                "Set the name of a local Ollama model (example: llama3.2)."
            )
        return

    raise ValueError(f"Unsupported GSD_LLM_PROVIDER: {provider!r}")


@dataclass(frozen=True)
class BrowserUseLLMs:
    primary: BaseChatModel
    fallback: BaseChatModel | None


def _create_llm(
    provider: LLMProvider, model: str, settings: Settings, *, timeout_s: float | None = None
) -> BaseChatModel:
    import browser_use  # type: ignore[import-not-found]

    if provider == "chatbrowseruse":
        timeout_kwargs = _provider_timeout_kwargs(browser_use.ChatBrowserUse, timeout_s)
        return browser_use.ChatBrowserUse(
            model=model,
            api_key=settings.browser_use_api_key,
            base_url=settings.browser_use_llm_url or None,
            **(timeout_kwargs or {}),
        )
    if provider == "openai":
        timeout_kwargs = _provider_timeout_kwargs(browser_use.ChatOpenAI, timeout_s)
        return browser_use.ChatOpenAI(
            model=model,
            api_key=settings.openai_api_key,
            add_schema_to_system_prompt=settings.openai_add_schema_to_system_prompt,
            dont_force_structured_output=settings.openai_dont_force_structured_output,
            **(timeout_kwargs or {}),
        )
    if provider == "ollama":
        timeout_kwargs = _provider_timeout_kwargs(browser_use.ChatOllama, timeout_s)
        return browser_use.ChatOllama(
            model=model,
            host=settings.ollama_host,
            **(timeout_kwargs or {}),
        )
    if provider == "anthropic":
        timeout_kwargs = _provider_timeout_kwargs(browser_use.ChatAnthropic, timeout_s)
        return browser_use.ChatAnthropic(
            model=model,
            api_key=settings.anthropic_api_key,
            **(timeout_kwargs or {}),
        )

    raise ValueError(f"Unsupported GSD_LLM_PROVIDER: {provider!r}")


def create_browser_use_llms(
    settings: Settings, *, timeout_s: float | None = None
) -> BrowserUseLLMs:
    """Create the browser-use BaseChatModels for the configured provider (and optional fallback)."""
    validate_llm_settings(settings)

    try:
        import browser_use  # type: ignore[import-not-found]  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "browser-use is not installed. Install gsd with the browser-use dependency."
        ) from exc

    fallback_provider = settings.fallback_llm_provider
    fallback_model = settings.fallback_model.strip()
    if fallback_provider is None and fallback_model:
        raise ValueError(
            "GSD_FALLBACK_MODEL is set but GSD_FALLBACK_LLM_PROVIDER is missing."
        )
    if fallback_provider is not None and not fallback_model:
        raise ValueError(
            "GSD_FALLBACK_LLM_PROVIDER is set but GSD_FALLBACK_MODEL is missing."
        )

    primary = _create_llm(settings.llm_provider, settings.model, settings, timeout_s=timeout_s)
    fallback = (
        _create_llm(fallback_provider, fallback_model, settings, timeout_s=timeout_s)
        if fallback_provider is not None and fallback_model
        else None
    )
    return BrowserUseLLMs(primary=primary, fallback=fallback)


def create_browser_use_llm(settings: Settings, *, timeout_s: float | None = None) -> BaseChatModel:
    """Create the browser-use BaseChatModel for the configured provider."""
    return create_browser_use_llms(settings, timeout_s=timeout_s).primary
