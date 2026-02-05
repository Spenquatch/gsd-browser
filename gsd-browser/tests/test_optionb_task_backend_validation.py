from __future__ import annotations

import pytest

from gsd_browser.optionb.task_backend import require_docket_redis_url, validate_docket_url


def test_validate_docket_url_rejects_missing() -> None:
    with pytest.raises(RuntimeError, match="FASTMCP_DOCKET_URL is required"):
        validate_docket_url("")


def test_validate_docket_url_rejects_memory_backend() -> None:
    with pytest.raises(RuntimeError, match="memory backend is forbidden"):
        validate_docket_url("memory://")


def test_require_docket_redis_url_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FASTMCP_DOCKET_URL", "redis://localhost:6379/0")
    assert require_docket_redis_url() == "redis://localhost:6379/0"
