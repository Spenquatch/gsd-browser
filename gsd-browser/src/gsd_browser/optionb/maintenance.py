from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Protocol

logger = logging.getLogger("gsd_browser.optionb.maintenance")


class SupportsRunOnce(Protocol):
    def run_once(self) -> Awaitable[bool]: ...


def _cleanup_interval_seconds() -> int:
    raw = str(os.environ.get("GSD_CLEANUP_INTERVAL_S", "")).strip()
    if not raw:
        return 300
    try:
        value = int(raw)
    except ValueError:
        return 300
    return value if value > 0 else 300


async def run_cleanup_maintenance_loop(
    runner: SupportsRunOnce,
    *,
    interval_seconds: int | None = None,
    on_leadership_change: Callable[[bool], None] | None = None,
) -> None:
    """Run cleanup on a fixed interval, tolerating failures.

    Canonical spec: `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` §4.3, §8.7.
    """
    interval_s = (
        int(interval_seconds) if interval_seconds is not None else _cleanup_interval_seconds()
    )
    last_leader: bool | None = None

    while True:
        try:
            acquired = await runner.run_once()
            if acquired:
                logger.info("maintenance.cleanup.leader_acquired")
            else:
                logger.debug("maintenance.cleanup.leader_skipped")
            if acquired != last_leader:
                last_leader = acquired
                if on_leadership_change is not None:
                    on_leadership_change(acquired)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("maintenance.cleanup.failed", extra={"error": str(exc)})

        await asyncio.sleep(float(interval_s))
