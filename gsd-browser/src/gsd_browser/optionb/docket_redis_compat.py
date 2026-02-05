from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

logger = logging.getLogger("gsd_browser.optionb.docket_redis_compat")

_PATCHED = False
_WARNED = False

T = TypeVar("T")


def apply_xautoclaim_compat_patch() -> None:
    """Patch redis-py to tolerate Redis servers without XAUTOCLAIM.

    Docket >= 0.16 uses Redis Streams consumer-group redelivery via XAUTOCLAIM.
    Redis 6.0 does not implement XAUTOCLAIM (it was added in Redis 6.2), which
    causes the background Docket worker task to crash.

    In long-running worker processes, this failure can be effectively silent
    because the task exception is not awaited, leaving jobs stuck in "queued".

    This patch makes `Redis.xautoclaim()` fall back to `XPENDING` + `XCLAIM`
    when the server responds with "unknown command 'XAUTOCLAIM'". This restores
    basic redelivery/reclaim behavior on Redis 6.0.
    """
    global _PATCHED
    if _PATCHED:
        return

    try:
        from redis.asyncio.client import Redis as AsyncRedis
        from redis.exceptions import ResponseError
    except Exception:  # noqa: BLE001
        # Redis optional/import issues; nothing to patch.
        _PATCHED = True
        return

    original: Callable[..., Awaitable[Any]] | None = getattr(AsyncRedis, "xautoclaim", None)
    if original is None:
        _PATCHED = True
        return

    if getattr(original, "__gsd_xautoclaim_compat__", False):
        _PATCHED = True
        return

    async def patched(self: Any, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        global _WARNED
        try:
            return await cast(Callable[..., Awaitable[Any]], original)(self, *args, **kwargs)
        except ResponseError as exc:
            message = str(exc).lower()
            if "unknown command" in message and "xautoclaim" in message:
                if not _WARNED:
                    _WARNED = True
                    logger.warning(
                        "redis.xautoclaim_unsupported",
                        extra={"error": str(exc)},
                    )
                name = kwargs.get("name")
                groupname = kwargs.get("groupname")
                consumername = kwargs.get("consumername")
                min_idle_time = kwargs.get("min_idle_time")
                count = kwargs.get("count")

                if name is None and len(args) > 0:
                    name = args[0]
                if groupname is None and len(args) > 1:
                    groupname = args[1]
                if consumername is None and len(args) > 2:
                    consumername = args[2]
                if min_idle_time is None and len(args) > 3:
                    min_idle_time = args[3]
                if count is None and len(args) > 5:
                    count = args[5]

                if (
                    name is None
                    or groupname is None
                    or consumername is None
                    or min_idle_time is None
                ):
                    return "0-0", [], []

                try:
                    pending = await self.xpending_range(  # type: ignore[attr-defined]
                        name,
                        groupname,
                        "-",
                        "+",
                        int(count) if count is not None else 50,
                    )
                except Exception:  # noqa: BLE001
                    return "0-0", [], []

                message_ids: list[str] = []
                for entry in pending or []:
                    msg_id = None
                    idle_ms = None
                    if isinstance(entry, dict):
                        msg_id = entry.get("message_id") or entry.get("id")
                        idle_ms = entry.get("time_since_delivered") or entry.get("idle")
                    elif isinstance(entry, (tuple, list)) and len(entry) >= 3:
                        msg_id = entry[0]
                        idle_ms = entry[2]

                    try:
                        if isinstance(msg_id, (bytes, bytearray)):
                            msg_id_str = msg_id.decode("utf-8")
                        else:
                            msg_id_str = str(msg_id)
                        idle_val = int(idle_ms) if idle_ms is not None else None
                    except Exception:  # noqa: BLE001
                        continue

                    if idle_val is None or idle_val < int(min_idle_time):
                        continue
                    message_ids.append(msg_id_str)

                if not message_ids:
                    return "0-0", [], []

                try:
                    claimed = await self.xclaim(  # type: ignore[attr-defined]
                        name,
                        groupname,
                        consumername,
                        int(min_idle_time),
                        message_ids,
                    )
                except Exception:  # noqa: BLE001
                    return "0-0", [], []

                return "0-0", claimed or [], []
            raise

    patched.__gsd_xautoclaim_compat__ = True  # type: ignore[attr-defined]
    AsyncRedis.xautoclaim = patched  # type: ignore[method-assign]
    _PATCHED = True
