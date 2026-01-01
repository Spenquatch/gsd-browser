"""Telemetry helpers for measuring streaming latency."""

from __future__ import annotations

import hashlib
import hmac
import math
from typing import Any


def hmac_sha256_hex(*, api_key: str, nonce: str) -> str:
    return hmac.new(api_key.encode("utf-8"), nonce.encode("utf-8"), hashlib.sha256).hexdigest()


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if p <= 0:
        return min(values)
    if p >= 100:
        return max(values)

    sorted_values = sorted(values)
    n = len(sorted_values)
    rank = int(math.ceil((p / 100.0) * n)) - 1
    rank = max(0, min(n - 1, rank))
    return float(sorted_values[rank])


def summarize_latency(
    *, server_latency_ms: list[float], client_delta_ms: list[float]
) -> dict[str, Any]:
    return {
        "count": len(server_latency_ms),
        "server_latency_ms": {
            "p50": percentile(server_latency_ms, 50),
            "p90": percentile(server_latency_ms, 90),
            "p95": percentile(server_latency_ms, 95),
            "p99": percentile(server_latency_ms, 99),
        },
        "client_delta_ms": {
            "p50": percentile(client_delta_ms, 50),
            "p90": percentile(client_delta_ms, 90),
            "p95": percentile(client_delta_ms, 95),
            "p99": percentile(client_delta_ms, 99),
        },
    }
