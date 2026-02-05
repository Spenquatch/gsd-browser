from __future__ import annotations

import asyncio

import pytest
from redis.exceptions import ResponseError

from gsd_browser.optionb import docket_redis_compat


def test_apply_xautoclaim_compat_patch_returns_empty_on_unknown_command() -> None:
    from redis.asyncio.client import Redis as AsyncRedis

    original = AsyncRedis.xautoclaim
    docket_redis_compat._PATCHED = False
    docket_redis_compat._WARNED = False

    async def unknown_command(self, *args: object, **kwargs: object) -> object:  # noqa: ANN001
        raise ResponseError(
            "unknown command `XAUTOCLAIM`, with args beginning with: `gsd:stream`"
        )

    try:
        AsyncRedis.xautoclaim = unknown_command  # type: ignore[method-assign]
        docket_redis_compat.apply_xautoclaim_compat_patch()

        result = asyncio.run(AsyncRedis.xautoclaim(object()))  # type: ignore[arg-type]
        assert result == ("0-0", [], [])
    finally:
        AsyncRedis.xautoclaim = original  # type: ignore[method-assign]
        docket_redis_compat._PATCHED = False
        docket_redis_compat._WARNED = False


def test_apply_xautoclaim_compat_patch_reraises_other_response_errors() -> None:
    from redis.asyncio.client import Redis as AsyncRedis

    original = AsyncRedis.xautoclaim
    docket_redis_compat._PATCHED = False
    docket_redis_compat._WARNED = False

    async def other_error(self, *args: object, **kwargs: object) -> object:  # noqa: ANN001
        raise ResponseError("NOGROUP No such key 'gsd:stream' or consumer group")

    try:
        AsyncRedis.xautoclaim = other_error  # type: ignore[method-assign]
        docket_redis_compat.apply_xautoclaim_compat_patch()

        with pytest.raises(ResponseError):
            asyncio.run(AsyncRedis.xautoclaim(object()))  # type: ignore[arg-type]
    finally:
        AsyncRedis.xautoclaim = original  # type: ignore[method-assign]
        docket_redis_compat._PATCHED = False
        docket_redis_compat._WARNED = False

