from __future__ import annotations

import logging

import pytest

from gsd_browser.streaming.security import (
    FixedWindowRateLimiter,
    NonceStore,
    StreamingAuthConfig,
    authorize_socket_connection,
    load_streaming_auth_config,
)
from gsd_browser.streaming.telemetry import hmac_sha256_hex


def test_load_streaming_auth_config_requires_api_key_when_auth_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STREAMING_AUTH_REQUIRED", "true")
    monkeypatch.delenv("STREAMING_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="STREAMING_API_KEY"):
        load_streaming_auth_config()


def test_nonce_store_rejects_replay_after_uses_exhausted() -> None:
    api_key = "test-api-key"
    store = NonceStore(ttl_seconds=60, uses=1)
    issued = store.issue()
    nonce = issued["nonce"]
    sig = hmac_sha256_hex(api_key=api_key, nonce=nonce)

    assert store.validate(nonce=nonce, sig_hex=sig, api_key=api_key) is True
    assert store.validate(nonce=nonce, sig_hex=sig, api_key=api_key) is False


def test_authorize_socket_connection_rejects_missing_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "gsd_browser.streaming.security.get_security_logger",
        lambda: logging.getLogger("test.security"),
    )

    config = StreamingAuthConfig(
        auth_required=True,
        api_key="test-api-key",
        allowed_origins=["https://dashboard.example"],
        nonce_ttl_seconds=60,
        nonce_uses=2,
        per_sid_events_per_minute=120,
        per_sid_connects_per_minute=30,
    )
    store = NonceStore(ttl_seconds=60, uses=1)
    limiter = FixedWindowRateLimiter(window_seconds=60, max_events=10)

    ok = authorize_socket_connection(
        config=config,
        nonce_store=store,
        namespace="/stream",
        sid="sid-1",
        environ={"HTTP_ORIGIN": "https://dashboard.example"},
        auth=None,
        connect_limiter=limiter,
    )
    assert ok is False


def test_authorize_socket_connection_accepts_valid_nonce_sig(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "gsd_browser.streaming.security.get_security_logger",
        lambda: logging.getLogger("test.security"),
    )

    api_key = "test-api-key"
    config = StreamingAuthConfig(
        auth_required=True,
        api_key=api_key,
        allowed_origins=["https://dashboard.example"],
        nonce_ttl_seconds=60,
        nonce_uses=2,
        per_sid_events_per_minute=120,
        per_sid_connects_per_minute=30,
    )
    store = NonceStore(ttl_seconds=60, uses=2)
    limiter = FixedWindowRateLimiter(window_seconds=60, max_events=10)
    issued = store.issue()
    nonce = issued["nonce"]

    ok = authorize_socket_connection(
        config=config,
        nonce_store=store,
        namespace="/stream",
        sid="sid-1",
        environ={"HTTP_ORIGIN": "https://dashboard.example"},
        auth={"nonce": nonce, "sig": hmac_sha256_hex(api_key=api_key, nonce=nonce)},
        connect_limiter=limiter,
    )
    assert ok is True


def test_authorize_socket_connection_rate_limits_connects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "gsd_browser.streaming.security.get_security_logger",
        lambda: logging.getLogger("test.security"),
    )

    api_key = "test-api-key"
    config = StreamingAuthConfig(
        auth_required=False,
        api_key=api_key,
        allowed_origins=None,
        nonce_ttl_seconds=60,
        nonce_uses=2,
        per_sid_events_per_minute=120,
        per_sid_connects_per_minute=30,
    )
    store = NonceStore(ttl_seconds=60, uses=2)
    limiter = FixedWindowRateLimiter(window_seconds=60, max_events=1)

    monkeypatch.setattr("gsd_browser.streaming.security.time.monotonic", lambda: 100.0)
    first = authorize_socket_connection(
        config=config,
        nonce_store=store,
        namespace="/stream",
        sid="sid-1",
        environ={},
        auth=None,
        connect_limiter=limiter,
    )
    second = authorize_socket_connection(
        config=config,
        nonce_store=store,
        namespace="/stream",
        sid="sid-1",
        environ={},
        auth=None,
        connect_limiter=limiter,
    )

    assert first is True
    assert second is False
