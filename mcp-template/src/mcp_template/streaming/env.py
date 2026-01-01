"""Environment helpers for browser streaming."""

from __future__ import annotations

from typing import Literal, cast

StreamingMode = Literal["cdp", "screenshot"]
StreamingQuality = Literal["low", "med", "high"]


def normalize_streaming_mode(value: str | None) -> StreamingMode:
    if not value:
        return "cdp"
    normalized = value.strip().lower()
    if normalized in ("cdp", "screenshot"):
        return cast(StreamingMode, normalized)
    return "cdp"


def normalize_streaming_quality(value: str | None) -> StreamingQuality:
    if not value:
        return "med"
    normalized = value.strip().lower()
    if normalized in ("low", "med", "high"):
        return cast(StreamingQuality, normalized)
    return "med"
