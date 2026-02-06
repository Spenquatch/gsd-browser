from __future__ import annotations

import os
from collections.abc import Mapping

DEFAULT_PRESIGNED_URL_TTL_S = 900
MIN_PRESIGNED_URL_TTL_S = 1
MAX_PRESIGNED_URL_TTL_S = 3600


def parse_presigned_url_ttl_s(
    raw: str | None,
    *,
    default: int = DEFAULT_PRESIGNED_URL_TTL_S,
    min_s: int = MIN_PRESIGNED_URL_TTL_S,
    max_s: int = MAX_PRESIGNED_URL_TTL_S,
) -> int:
    """Parse and clamp a presigned URL TTL in seconds.

    - Empty/invalid values fall back to `default`.
    - Valid integer values are clamped to [min_s, max_s].
    """
    text = str(raw or "").strip()
    if not text:
        return int(default)
    try:
        value = int(text)
    except ValueError:
        return int(default)
    return min(max(int(value), int(min_s)), int(max_s))


def presigned_url_ttl_s_from_env(env: Mapping[str, str] | None = None) -> int:
    source = os.environ if env is None else env
    return parse_presigned_url_ttl_s(source.get("GSD_PRESIGNED_URL_TTL_S", ""))

