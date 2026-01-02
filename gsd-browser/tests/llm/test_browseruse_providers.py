from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

# These tests are intended to activate once B4-code lands the `browser-use` dependency and
# provider-selection plumbing. Until then, they should skip cleanly (even if `browser_use`
# happens to be installed globally).
_project_root = Path(__file__).resolve().parents[2]
_pyproject = _project_root / "pyproject.toml"
_deps = []
if _pyproject.exists():
    data = tomllib.loads(_pyproject.read_text(encoding="utf-8"))
    _deps = (data.get("project") or {}).get("dependencies") or []
_browser_use_declared = any(str(dep).strip().startswith("browser-use") for dep in _deps)


def _require_browser_use() -> None:
    if not _browser_use_declared:
        pytest.skip("browser-use dependency not declared yet (B4-code not merged)")
    try:
        import browser_use as _unused_browser_use  # noqa: F401
    except Exception:  # noqa: BLE001
        pytest.skip("browser_use is not importable (deps not installed?)")


@dataclass(frozen=True, slots=True)
class _Created:
    kind: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


def _patch_provider_classes(monkeypatch: pytest.MonkeyPatch, module: Any) -> list[_Created]:
    created: list[_Created] = []

    class DummyChatBrowserUse:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            created.append(_Created("chatbrowseruse", args, kwargs))

    class DummyChatOllama:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            created.append(_Created("ollama", args, kwargs))

    monkeypatch.setattr(module, "ChatBrowserUse", DummyChatBrowserUse, raising=False)
    monkeypatch.setattr(module, "ChatOllama", DummyChatOllama, raising=False)
    monkeypatch.setattr(module, "Ollama", DummyChatOllama, raising=False)

    return created


def test_cli_llm_provider_overrides_env_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    _require_browser_use()
    from gsd_browser.llm import browseruse_providers as providers

    created = _patch_provider_classes(monkeypatch, providers)

    llm = providers.get_browser_use_llm(
        llm_provider="chatbrowseruse",
        env={"GSD_BROWSER_LLM_PROVIDER": "ollama", "BROWSER_USE_API_KEY": "test-key"},
    )

    assert llm is not None
    assert [item.kind for item in created] == ["chatbrowseruse"]


def test_env_llm_provider_used_when_cli_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    _require_browser_use()
    from gsd_browser.llm import browseruse_providers as providers

    created = _patch_provider_classes(monkeypatch, providers)

    llm = providers.get_browser_use_llm(
        llm_provider=None,
        env={"GSD_BROWSER_LLM_PROVIDER": "ollama"},
    )

    assert llm is not None
    assert [item.kind for item in created] == ["ollama"]


def test_cloud_provider_missing_api_key_errors_helpfully(monkeypatch: pytest.MonkeyPatch) -> None:
    _require_browser_use()
    from gsd_browser.llm import browseruse_providers as providers

    _patch_provider_classes(monkeypatch, providers)

    with pytest.raises(RuntimeError) as excinfo:
        providers.get_browser_use_llm(
            llm_provider="chatbrowseruse",
            env={"GSD_BROWSER_LLM_PROVIDER": "chatbrowseruse"},
        )

    message = str(excinfo.value)
    assert "BROWSER_USE_API_KEY" in message
    assert "chatbrowseruse" in message.lower()


def test_oss_provider_does_not_require_cloud_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _require_browser_use()
    from gsd_browser.llm import browseruse_providers as providers

    created = _patch_provider_classes(monkeypatch, providers)

    llm = providers.get_browser_use_llm(llm_provider="ollama", env={})

    assert llm is not None
    assert [item.kind for item in created] == ["ollama"]
