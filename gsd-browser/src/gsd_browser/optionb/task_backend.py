"""Option B task backend validation helpers (Docket + Redis).

Canonical spec: `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` §8.4.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse


def validate_docket_url(url: str) -> None:
    """Validate that the Docket backend is Redis/Valkey (no memory backend)."""

    raw = str(url).strip()
    if not raw:
        raise RuntimeError("FASTMCP_DOCKET_URL is required for Option B tasks")

    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme in {"memory"}:
        raise RuntimeError("FASTMCP_DOCKET_URL must be a Redis URL (memory backend is forbidden)")
    if scheme not in {"redis", "rediss"}:
        raise RuntimeError(
            f"FASTMCP_DOCKET_URL must be a Redis URL (got scheme={scheme!r}, url={raw!r})"
        )


def require_docket_redis_url() -> str:
    """Return the configured Docket URL after enforcing Option B invariants."""

    url = str(os.environ.get("FASTMCP_DOCKET_URL", "")).strip()
    validate_docket_url(url)
    try:
        import fastmcp

        fastmcp.settings.docket.url = url
    except Exception:  # noqa: BLE001
        # Best-effort: only needed for environments that mutate env at runtime.
        pass
    return url
