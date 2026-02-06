from __future__ import annotations

import pytest

from gsd_browser.optionb.artifact_delivery import (
    DEFAULT_PRESIGNED_URL_TTL_S,
    MAX_PRESIGNED_URL_TTL_S,
    MIN_PRESIGNED_URL_TTL_S,
    parse_presigned_url_ttl_s,
    presigned_url_ttl_s_from_env,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, DEFAULT_PRESIGNED_URL_TTL_S),
        ("", DEFAULT_PRESIGNED_URL_TTL_S),
        ("   ", DEFAULT_PRESIGNED_URL_TTL_S),
        ("nope", DEFAULT_PRESIGNED_URL_TTL_S),
        ("900", 900),
        (" 901 ", 901),
        ("0", MIN_PRESIGNED_URL_TTL_S),
        ("-5", MIN_PRESIGNED_URL_TTL_S),
        (str(MAX_PRESIGNED_URL_TTL_S + 1), MAX_PRESIGNED_URL_TTL_S),
        ("999999", MAX_PRESIGNED_URL_TTL_S),
    ],
)
def test_parse_presigned_url_ttl_s_clamps_and_defaults(raw: str | None, expected: int) -> None:
    assert parse_presigned_url_ttl_s(raw) == expected


def test_presigned_url_ttl_s_from_env_uses_mapping_override() -> None:
    assert presigned_url_ttl_s_from_env({"GSD_PRESIGNED_URL_TTL_S": "12"}) == 12
    assert (
        presigned_url_ttl_s_from_env({"GSD_PRESIGNED_URL_TTL_S": "0"})
        == MIN_PRESIGNED_URL_TTL_S
    )
    assert (
        presigned_url_ttl_s_from_env({"GSD_PRESIGNED_URL_TTL_S": "999999"})
        == MAX_PRESIGNED_URL_TTL_S
    )

