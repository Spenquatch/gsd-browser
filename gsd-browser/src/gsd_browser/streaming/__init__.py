"""Browser streaming primitives (CDP and screenshot fallback)."""

from .env import (
    StreamingMode,
    StreamingQuality,
    normalize_streaming_mode,
    normalize_streaming_quality,
)
from .stats import StreamingStats

__all__ = [
    "StreamingMode",
    "StreamingQuality",
    "StreamingStats",
    "normalize_streaming_mode",
    "normalize_streaming_quality",
]
