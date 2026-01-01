from __future__ import annotations

import asyncio
import importlib
import inspect
import runpy
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

import pytest


def _run(value: Any) -> Any:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


def _resolve_security_module() -> Any | None:
    candidates = [
        "gsd_browser.streaming.security",
        "gsd_browser.streaming.auth",
        "gsd_browser.dashboard.security",
        "gsd_browser.dashboard.auth",
        "gsd_browser.security",
        "gsd_browser.auth",
    ]
    for module_name in candidates:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        if all(
            hasattr(module, name)
            for name in ("ensure_authenticated", "_issue_nonce_for_sid", "_verify_nonce_for_sid")
        ):
            return module
    return None


def _invoke(fn: Callable[..., Any], **kwargs: Any) -> Any:
    sig = inspect.signature(fn)
    parameters = list(sig.parameters.values())

    if any(param.kind == param.VAR_KEYWORD for param in parameters):
        return fn(**kwargs)

    args: list[Any] = []
    call_kwargs: dict[str, Any] = {}

    for param in parameters:
        if param.kind == param.VAR_POSITIONAL:
            continue
        if param.kind == param.KEYWORD_ONLY:
            if param.name in kwargs:
                call_kwargs[param.name] = kwargs[param.name]
            elif param.default is inspect._empty:
                raise TypeError(f"Missing required keyword-only argument: {param.name}")
            continue
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
            if param.name in kwargs:
                args.append(kwargs[param.name])
            elif param.default is inspect._empty:
                raise TypeError(f"Missing required positional argument: {param.name}")
            continue

    if any(param.kind == param.POSITIONAL_ONLY for param in parameters) and call_kwargs:
        return fn(*args)

    return fn(*args, **call_kwargs)


def _assert_rejected(result: Any) -> None:
    if result is False:
        return
    if isinstance(result, Mapping) and result.get("ok") is False:
        return
    raise AssertionError(f"Expected auth rejection, got: {result!r}")


def _assert_accepted(result: Any) -> None:
    if result is False:
        raise AssertionError("Expected auth acceptance, got False")


def test_ensure_authenticated_rejects_missing_api_key_when_required() -> None:
    module = _resolve_security_module()
    if module is None:
        pytest.skip("Dashboard security module not yet implemented (B2-code pending)")

    ensure_authenticated = getattr(module, "ensure_authenticated")

    sid = "sid-123"
    origin = "https://dashboard.example"
    auth: dict[str, Any] = {}
    environ = {"HTTP_ORIGIN": origin}

    try:
        result = _run(
            _invoke(
                ensure_authenticated,
                sid=sid,
                environ=environ,
                auth=auth,
                api_key="test-api-key",
                allowed_origins=[origin],
                auth_required=True,
                now=100.0,
            )
        )
    except Exception:
        return

    _assert_rejected(result)


def test_ensure_authenticated_rejects_disallowed_origin() -> None:
    module = _resolve_security_module()
    if module is None:
        pytest.skip("Dashboard security module not yet implemented (B2-code pending)")

    ensure_authenticated = getattr(module, "ensure_authenticated")

    sid = "sid-123"
    auth = {"api_key": "test-api-key"}
    environ = {"HTTP_ORIGIN": "https://evil.example"}

    try:
        result = _run(
            _invoke(
                ensure_authenticated,
                sid=sid,
                environ=environ,
                auth=auth,
                api_key="test-api-key",
                allowed_origins=["https://dashboard.example"],
                auth_required=True,
                now=100.0,
            )
        )
    except Exception:
        return

    _assert_rejected(result)


def test_ensure_authenticated_accepts_valid_api_key_and_origin() -> None:
    module = _resolve_security_module()
    if module is None:
        pytest.skip("Dashboard security module not yet implemented (B2-code pending)")

    ensure_authenticated = getattr(module, "ensure_authenticated")

    sid = "sid-123"
    origin = "https://dashboard.example"
    auth = {"api_key": "test-api-key"}
    environ = {"HTTP_ORIGIN": origin}

    result = _run(
        _invoke(
            ensure_authenticated,
            sid=sid,
            environ=environ,
            auth=auth,
            api_key="test-api-key",
            allowed_origins=[origin],
            auth_required=True,
            now=100.0,
        )
    )
    _assert_accepted(result)


def _normalize_nonce_response(response: Any) -> tuple[str, str]:
    if isinstance(response, tuple) and len(response) == 2:
        nonce, signature = response
        return str(nonce), str(signature)
    if isinstance(response, Mapping):
        nonce = response.get("nonce")
        signature = response.get("signature")
        if nonce is not None and signature is not None:
            return str(nonce), str(signature)
    raise TypeError(f"Unsupported nonce response: {response!r}")


def test_nonce_issue_and_verify_roundtrip() -> None:
    module = _resolve_security_module()
    if module is None:
        pytest.skip("Dashboard security module not yet implemented (B2-code pending)")

    issue_nonce = getattr(module, "_issue_nonce_for_sid")
    verify_nonce = getattr(module, "_verify_nonce_for_sid")

    sid = "sid-abc"
    api_key = "test-api-key"

    issued = _run(_invoke(issue_nonce, sid=sid, api_key=api_key, now=100.0))
    nonce, signature = _normalize_nonce_response(issued)

    ok = _run(
        _invoke(
            verify_nonce,
            sid=sid,
            api_key=api_key,
            nonce=nonce,
            signature=signature,
            now=100.1,
        )
    )
    assert ok is True

    bad = _run(
        _invoke(
            verify_nonce,
            sid=sid,
            api_key=api_key,
            nonce=nonce,
            signature="bad",
            now=100.2,
        )
    )
    assert bad is False


def _resolve_rate_limiter(module: Any) -> Any | None:
    for name in ("SidRateLimiter", "RateLimiter", "SocketRateLimiter"):
        cls = getattr(module, name, None)
        if cls is not None:
            return cls
    return None


def _instantiate_rate_limiter(cls: type[Any]) -> Any:
    sig = inspect.signature(cls)
    kwargs: dict[str, Any] = {}
    for name in sig.parameters:
        if name in ("self",):
            continue
        if name in ("max_events", "limit", "capacity", "max_per_window", "max_requests"):
            kwargs[name] = 2
        elif name in ("window_seconds", "period_seconds", "per_seconds", "window", "period"):
            kwargs[name] = 1.0
        elif name in ("enabled",):
            kwargs[name] = True
    return cls(**kwargs)


def _resolve_rate_limiter_method(limiter: Any) -> Callable[..., Any] | None:
    for name in ("allow", "check", "acquire", "__call__"):
        meth = getattr(limiter, name, None)
        if callable(meth):
            return meth
    return None


def test_rate_limiter_blocks_after_limit_within_window(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _resolve_security_module()
    if module is None:
        pytest.skip("Dashboard security module not yet implemented (B2-code pending)")

    cls = _resolve_rate_limiter(module)
    if cls is None:
        pytest.skip("Rate limiter not yet implemented in security module")

    limiter = _instantiate_rate_limiter(cls)
    method = _resolve_rate_limiter_method(limiter)
    if method is None:
        pytest.skip("Rate limiter API not yet stable (missing allow/check/acquire)")

    clock = {"now": 100.0}

    limiter_module = importlib.import_module(cls.__module__)
    if hasattr(limiter_module, "time") and hasattr(limiter_module.time, "time"):
        monkeypatch.setattr(limiter_module.time, "time", lambda: clock["now"])
    if hasattr(limiter_module, "time") and callable(getattr(limiter_module, "time")):
        monkeypatch.setattr(limiter_module, "time", lambda: clock["now"])

    sid = "sid-rate"

    def call_once() -> Any:
        return _run(_invoke(method, sid=sid, key=sid, now=clock["now"]))

    r1 = call_once()
    r2 = call_once()
    r3 = call_once()

    assert r1 is not False
    assert r2 is not False
    assert r3 is False

    clock["now"] += 2.0
    r4 = call_once()
    assert r4 is not False


def _resolve_latency_parser(namespace: dict[str, Any]) -> Callable[..., Any] | None:
    for name in (
        "parse_latency_json",
        "parse_latency_payload",
        "parse_latency_event",
        "_parse_latency_event",
    ):
        fn = namespace.get(name)
        if callable(fn):
            return fn
    return None


def test_telemetry_script_parses_latency_payload() -> None:
    script_candidates = [
        Path(__file__).resolve().parents[2] / "scripts" / "measure_stream_latency.py",
        Path(__file__).resolve().parents[3] / "scripts" / "measure_stream_latency.py",
    ]
    script_path = next((path for path in script_candidates if path.exists()), None)
    if script_path is None:
        pytest.skip("measure_stream_latency.py not yet present (B2-code pending)")

    namespace = runpy.run_path(str(script_path))
    parser = _resolve_latency_parser(namespace)
    if parser is None:
        pytest.skip("Telemetry script lacks a stable latency parser helper")

    payload = {"timestamp": 100.0, "client_received_ts": 100.123}
    result = parser(payload)
    assert isinstance(result, (int, float))
