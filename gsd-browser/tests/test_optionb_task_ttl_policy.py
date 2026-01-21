"""Unit tests for task TTL policy enforcement.

Tests the task_ttl_policy module in isolation, verifying:
- Default TTLs are applied when client doesn't provide one
- Client TTL override is ignored when flag is disabled
- Client TTL override is rejected when out of bounds
- Client TTL override is accepted when within bounds and enabled
"""

from __future__ import annotations

import pytest

from gsd_browser.optionb.task_ttl_policy import (
    DEFAULT_TTL_MAX_S,
    DEFAULT_TTL_MIN_S,
    DEFAULT_TTL_WEB_EVAL_AGENT_S,
    DEFAULT_TTL_WEB_TASK_AGENT_GITHUB_S,
    DEFAULT_TTL_WEB_TASK_AGENT_S,
    TaskTTLConfig,
    TTLOutOfBoundsError,
    compute_effective_ttl_ms,
    reset_ttl_config_cache,
)


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    """Reset the module-level config cache before each test."""
    reset_ttl_config_cache()
    yield
    reset_ttl_config_cache()


class TestTaskTTLConfig:
    """Tests for TaskTTLConfig loading."""

    def test_from_env_uses_defaults_when_no_env_vars(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Clear all relevant env vars
        for var in [
            "GSD_TASK_ALLOW_CLIENT_TTL_OVERRIDE",
            "GSD_TASK_TTL_MIN_S",
            "GSD_TASK_TTL_MAX_S",
            "GSD_TASK_TTL_WEB_EVAL_AGENT_S",
            "GSD_TASK_TTL_WEB_TASK_AGENT_S",
            "GSD_TASK_TTL_WEB_TASK_AGENT_GITHUB_S",
        ]:
            monkeypatch.delenv(var, raising=False)

        config = TaskTTLConfig.from_env()

        assert config.allow_client_override is False
        assert config.min_ttl_s == DEFAULT_TTL_MIN_S
        assert config.max_ttl_s == DEFAULT_TTL_MAX_S
        assert config.default_web_eval_agent_s == DEFAULT_TTL_WEB_EVAL_AGENT_S
        assert config.default_web_task_agent_s == DEFAULT_TTL_WEB_TASK_AGENT_S
        assert config.default_web_task_agent_github_s == DEFAULT_TTL_WEB_TASK_AGENT_GITHUB_S

    def test_from_env_reads_custom_values(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GSD_TASK_ALLOW_CLIENT_TTL_OVERRIDE", "true")
        monkeypatch.setenv("GSD_TASK_TTL_MIN_S", "30")
        monkeypatch.setenv("GSD_TASK_TTL_MAX_S", "3600")
        monkeypatch.setenv("GSD_TASK_TTL_WEB_EVAL_AGENT_S", "600")
        monkeypatch.setenv("GSD_TASK_TTL_WEB_TASK_AGENT_S", "1200")
        monkeypatch.setenv("GSD_TASK_TTL_WEB_TASK_AGENT_GITHUB_S", "2400")

        config = TaskTTLConfig.from_env()

        assert config.allow_client_override is True
        assert config.min_ttl_s == 30
        assert config.max_ttl_s == 3600
        assert config.default_web_eval_agent_s == 600
        assert config.default_web_task_agent_s == 1200
        assert config.default_web_task_agent_github_s == 2400

    def test_get_default_ttl_s_returns_correct_per_tool_defaults(self) -> None:
        config = TaskTTLConfig(
            allow_client_override=False,
            min_ttl_s=60,
            max_ttl_s=7200,
            default_web_eval_agent_s=100,
            default_web_task_agent_s=200,
            default_web_task_agent_github_s=300,
        )

        assert config.get_default_ttl_s("web_eval_agent") == 100
        assert config.get_default_ttl_s("web_task_agent") == 200
        assert config.get_default_ttl_s("web_task_agent_github") == 300
        # Unknown tools fall back to web_eval_agent default
        assert config.get_default_ttl_s("unknown_tool") == 100


class TestComputeEffectiveTTL:
    """Tests for compute_effective_ttl_ms function."""

    def test_uses_default_when_client_ttl_is_none(self) -> None:
        config = TaskTTLConfig(
            allow_client_override=False,
            min_ttl_s=60,
            max_ttl_s=7200,
            default_web_eval_agent_s=900,
            default_web_task_agent_s=1800,
            default_web_task_agent_github_s=1800,
        )

        result = compute_effective_ttl_ms(
            tool_name="web_eval_agent",
            client_ttl_ms=None,
            config=config,
        )

        assert result == 900 * 1000  # 900 seconds in ms

    def test_uses_default_when_client_ttl_is_zero(self) -> None:
        config = TaskTTLConfig(
            allow_client_override=True,  # Even when override is allowed
            min_ttl_s=60,
            max_ttl_s=7200,
            default_web_eval_agent_s=900,
            default_web_task_agent_s=1800,
            default_web_task_agent_github_s=1800,
        )

        result = compute_effective_ttl_ms(
            tool_name="web_eval_agent",
            client_ttl_ms=0,
            config=config,
        )

        assert result == 900 * 1000

    def test_uses_default_when_client_ttl_is_negative(self) -> None:
        config = TaskTTLConfig(
            allow_client_override=True,
            min_ttl_s=60,
            max_ttl_s=7200,
            default_web_eval_agent_s=900,
            default_web_task_agent_s=1800,
            default_web_task_agent_github_s=1800,
        )

        result = compute_effective_ttl_ms(
            tool_name="web_eval_agent",
            client_ttl_ms=-1000,
            config=config,
        )

        assert result == 900 * 1000

    def test_ignores_client_ttl_when_override_disabled(self) -> None:
        config = TaskTTLConfig(
            allow_client_override=False,  # Override disabled
            min_ttl_s=60,
            max_ttl_s=7200,
            default_web_eval_agent_s=900,
            default_web_task_agent_s=1800,
            default_web_task_agent_github_s=1800,
        )

        # Client requests 5 minutes, but override is disabled
        result = compute_effective_ttl_ms(
            tool_name="web_eval_agent",
            client_ttl_ms=300_000,  # 5 minutes in ms
            config=config,
        )

        # Should use server default, not client request
        assert result == 900 * 1000

    def test_accepts_client_ttl_within_bounds_when_override_enabled(self) -> None:
        config = TaskTTLConfig(
            allow_client_override=True,
            min_ttl_s=60,
            max_ttl_s=7200,
            default_web_eval_agent_s=900,
            default_web_task_agent_s=1800,
            default_web_task_agent_github_s=1800,
        )

        # Client requests 5 minutes (within bounds)
        result = compute_effective_ttl_ms(
            tool_name="web_eval_agent",
            client_ttl_ms=300_000,  # 5 minutes in ms
            config=config,
        )

        # Should use client request
        assert result == 300_000

    def test_rejects_client_ttl_below_min_when_override_enabled(self) -> None:
        config = TaskTTLConfig(
            allow_client_override=True,
            min_ttl_s=60,
            max_ttl_s=7200,
            default_web_eval_agent_s=900,
            default_web_task_agent_s=1800,
            default_web_task_agent_github_s=1800,
        )

        # Client requests 30 seconds (below 60s min)
        with pytest.raises(TTLOutOfBoundsError) as exc_info:
            compute_effective_ttl_ms(
                tool_name="web_eval_agent",
                client_ttl_ms=30_000,  # 30 seconds in ms
                config=config,
            )

        assert exc_info.value.requested_s == 30
        assert exc_info.value.min_s == 60
        assert exc_info.value.max_s == 7200

    def test_rejects_client_ttl_above_max_when_override_enabled(self) -> None:
        config = TaskTTLConfig(
            allow_client_override=True,
            min_ttl_s=60,
            max_ttl_s=7200,
            default_web_eval_agent_s=900,
            default_web_task_agent_s=1800,
            default_web_task_agent_github_s=1800,
        )

        # Client requests 3 hours (above 2 hour max)
        with pytest.raises(TTLOutOfBoundsError) as exc_info:
            compute_effective_ttl_ms(
                tool_name="web_eval_agent",
                client_ttl_ms=10_800_000,  # 3 hours in ms
                config=config,
            )

        assert exc_info.value.requested_s == 10_800
        assert exc_info.value.min_s == 60
        assert exc_info.value.max_s == 7200

    def test_uses_correct_default_for_each_tool(self) -> None:
        config = TaskTTLConfig(
            allow_client_override=False,
            min_ttl_s=60,
            max_ttl_s=7200,
            default_web_eval_agent_s=100,
            default_web_task_agent_s=200,
            default_web_task_agent_github_s=300,
        )

        assert compute_effective_ttl_ms(
            tool_name="web_eval_agent", client_ttl_ms=None, config=config
        ) == 100_000

        assert compute_effective_ttl_ms(
            tool_name="web_task_agent", client_ttl_ms=None, config=config
        ) == 200_000

        assert compute_effective_ttl_ms(
            tool_name="web_task_agent_github", client_ttl_ms=None, config=config
        ) == 300_000

    def test_accepts_exact_min_boundary(self) -> None:
        config = TaskTTLConfig(
            allow_client_override=True,
            min_ttl_s=60,
            max_ttl_s=7200,
            default_web_eval_agent_s=900,
            default_web_task_agent_s=1800,
            default_web_task_agent_github_s=1800,
        )

        # Exactly at min boundary should be accepted
        result = compute_effective_ttl_ms(
            tool_name="web_eval_agent",
            client_ttl_ms=60_000,
            config=config,
        )

        assert result == 60_000

    def test_accepts_exact_max_boundary(self) -> None:
        config = TaskTTLConfig(
            allow_client_override=True,
            min_ttl_s=60,
            max_ttl_s=7200,
            default_web_eval_agent_s=900,
            default_web_task_agent_s=1800,
            default_web_task_agent_github_s=1800,
        )

        # Exactly at max boundary should be accepted
        result = compute_effective_ttl_ms(
            tool_name="web_eval_agent",
            client_ttl_ms=7_200_000,
            config=config,
        )

        assert result == 7_200_000

    def test_rejects_one_ms_over_max_boundary(self) -> None:
        """Verify ms-level precision: max_s*1000 + 1 ms is rejected."""
        config = TaskTTLConfig(
            allow_client_override=True,
            min_ttl_s=60,
            max_ttl_s=7200,
            default_web_eval_agent_s=900,
            default_web_task_agent_s=1800,
            default_web_task_agent_github_s=1800,
        )

        # 7200.001 seconds (1ms over max) should be rejected
        with pytest.raises(TTLOutOfBoundsError) as exc_info:
            compute_effective_ttl_ms(
                tool_name="web_eval_agent",
                client_ttl_ms=7_200_001,
                config=config,
            )

        # Error reports ceiling: (7200001 + 999) // 1000 = 7201
        assert exc_info.value.requested_s == 7201
        assert exc_info.value.max_s == 7200

    def test_rejects_max_plus_999ms_edge_case(self) -> None:
        """Regression test: max_s*1000 + 999 ms must NOT slip through.

        This was the original bug where floor division allowed this edge case.
        """
        config = TaskTTLConfig(
            allow_client_override=True,
            min_ttl_s=60,
            max_ttl_s=7200,
            default_web_eval_agent_s=900,
            default_web_task_agent_s=1800,
            default_web_task_agent_github_s=1800,
        )

        # 7200.999 seconds - previously this slipped through due to flooring
        with pytest.raises(TTLOutOfBoundsError) as exc_info:
            compute_effective_ttl_ms(
                tool_name="web_eval_agent",
                client_ttl_ms=7_200_999,
                config=config,
            )

        # Error reports ceiling: (7200999 + 999) // 1000 = 7201
        assert exc_info.value.requested_s == 7201
        assert exc_info.value.max_s == 7200

    def test_rejects_one_ms_under_min_boundary(self) -> None:
        """Verify ms-level precision: min_s*1000 - 1 ms is rejected."""
        config = TaskTTLConfig(
            allow_client_override=True,
            min_ttl_s=60,
            max_ttl_s=7200,
            default_web_eval_agent_s=900,
            default_web_task_agent_s=1800,
            default_web_task_agent_github_s=1800,
        )

        # 59.999 seconds (1ms under min) should be rejected
        with pytest.raises(TTLOutOfBoundsError) as exc_info:
            compute_effective_ttl_ms(
                tool_name="web_eval_agent",
                client_ttl_ms=59_999,
                config=config,
            )

        # Error reports ceiling: (59999 + 999) // 1000 = 60
        assert exc_info.value.requested_s == 60
        assert exc_info.value.min_s == 60


class TestTTLOutOfBoundsError:
    """Tests for TTLOutOfBoundsError exception."""

    def test_error_message_format(self) -> None:
        error = TTLOutOfBoundsError(requested_s=30, min_s=60, max_s=7200)

        assert "30s" in str(error)
        assert "60s" in str(error)
        assert "7200s" in str(error)
        assert "outside allowed bounds" in str(error)

    def test_error_attributes(self) -> None:
        error = TTLOutOfBoundsError(requested_s=100, min_s=200, max_s=300)

        assert error.requested_s == 100
        assert error.min_s == 200
        assert error.max_s == 300
