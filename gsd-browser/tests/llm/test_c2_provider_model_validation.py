from __future__ import annotations

import pytest

from gsd_browser.config import load_settings
from gsd_browser.llm.browser_use import create_browser_use_llm, validate_llm_settings


def test_c2_chatbrowseruse_missing_api_key_fails_fast_with_guidance() -> None:
    settings = load_settings(
        env={
            "GSD_BROWSER_LLM_PROVIDER": "chatbrowseruse",
            "GSD_BROWSER_MODEL": "bu-latest",
            "BROWSER_USE_API_KEY": "",
        },
        env_file=None,
    )

    with pytest.raises(ValueError) as excinfo:
        validate_llm_settings(settings)

    message = str(excinfo.value)
    assert "BROWSER_USE_API_KEY" in message
    assert "GSD_BROWSER_LLM_PROVIDER=chatbrowseruse" in message


def test_c2_chatbrowseruse_invalid_model_fails_fast_with_guidance() -> None:
    settings = load_settings(
        env={
            "GSD_BROWSER_LLM_PROVIDER": "chatbrowseruse",
            "GSD_BROWSER_MODEL": "gpt-4.1",
            "BROWSER_USE_API_KEY": "test-key",
        },
        env_file=None,
    )

    with pytest.raises(ValueError) as excinfo:
        validate_llm_settings(settings)

    message = str(excinfo.value)
    assert "Invalid GSD_BROWSER_MODEL" in message
    assert "bu-latest" in message
    assert "bu-1-0" in message
    assert "browser-use/<model>" in message


@pytest.mark.parametrize(
    ("provider", "required_env_var"),
    [
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("ollama", "OLLAMA_HOST"),
    ],
)
def test_c2_provider_missing_credentials_fails_fast_with_guidance(
    provider: str, required_env_var: str
) -> None:
    settings = load_settings(
        env={
            "GSD_BROWSER_LLM_PROVIDER": provider,
            "GSD_BROWSER_MODEL": "ignored-model",
            required_env_var: "",
        },
        env_file=None,
    )

    with pytest.raises(ValueError) as excinfo:
        validate_llm_settings(settings)

    message = str(excinfo.value)
    assert required_env_var in message
    assert f"GSD_BROWSER_LLM_PROVIDER={provider}" in message


def test_c2_create_browser_use_llm_does_not_mask_validation_errors() -> None:
    settings = load_settings(
        env={
            "GSD_BROWSER_LLM_PROVIDER": "openai",
            "GSD_BROWSER_MODEL": "gpt-4.1",
            "OPENAI_API_KEY": "",
        },
        env_file=None,
    )

    with pytest.raises(ValueError) as excinfo:
        create_browser_use_llm(settings)

    assert "Missing OPENAI_API_KEY" in str(excinfo.value)
