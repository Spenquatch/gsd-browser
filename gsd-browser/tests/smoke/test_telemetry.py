from __future__ import annotations

from gsd_browser.streaming.telemetry import hmac_sha256_hex, percentile, summarize_latency


def test_hmac_sha256_hex_matches_known_value() -> None:
    assert (
        hmac_sha256_hex(api_key="secret", nonce="abc")
        == "9946dad4e00e913fc8be8e5d3f7e110a4a9e832f83fb09c345285d78638d8a0e"
    )


def test_percentile_nearest_rank() -> None:
    values = [10.0, 1.0, 7.0, 3.0, 20.0]
    assert percentile(values, 0) == 1.0
    assert percentile(values, 50) == 7.0
    assert percentile(values, 95) == 20.0
    assert percentile(values, 100) == 20.0


def test_summarize_latency_shapes() -> None:
    report = summarize_latency(server_latency_ms=[1.0, 2.0, 3.0], client_delta_ms=[4.0, 5.0])
    assert report["count"] == 3
    assert report["server_latency_ms"]["p95"] is not None
    assert report["client_delta_ms"]["p50"] is not None
