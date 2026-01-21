from __future__ import annotations

import pytest

from gsd_browser.optionb.s3_client import S3Client, S3Config, has_complete_s3_config


def test_has_complete_s3_config_returns_false_when_no_vars_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no S3 env vars are set, has_complete_s3_config returns False."""
    for name in (
        "GSD_S3_ENDPOINT_URL",
        "GSD_S3_BUCKET",
        "GSD_S3_REGION",
        "GSD_S3_ACCESS_KEY_ID",
        "GSD_S3_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    assert has_complete_s3_config() is False


def test_has_complete_s3_config_returns_false_for_partial_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When only some S3 env vars are set (partial config), returns False.

    This prevents confusing errors where the code thinks S3 is enabled but
    S3Config.from_env() fails due to missing vars.
    """
    for name in (
        "GSD_S3_ENDPOINT_URL",
        "GSD_S3_BUCKET",
        "GSD_S3_REGION",
        "GSD_S3_ACCESS_KEY_ID",
        "GSD_S3_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    # Set only GSD_S3_ENDPOINT_URL (the old buggy check)
    monkeypatch.setenv("GSD_S3_ENDPOINT_URL", "http://s3.test")

    assert has_complete_s3_config() is False


def test_has_complete_s3_config_returns_true_when_all_vars_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When all required S3 env vars are set, returns True."""
    monkeypatch.setenv("GSD_S3_ENDPOINT_URL", "http://s3.test")
    monkeypatch.setenv("GSD_S3_BUCKET", "test-bucket")
    monkeypatch.setenv("GSD_S3_REGION", "us-east-1")
    monkeypatch.setenv("GSD_S3_ACCESS_KEY_ID", "test-key")
    monkeypatch.setenv("GSD_S3_SECRET_ACCESS_KEY", "test-secret")

    assert has_complete_s3_config() is True


def test_s3_config_from_env_requires_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "GSD_S3_ENDPOINT_URL",
        "GSD_S3_BUCKET",
        "GSD_S3_REGION",
        "GSD_S3_ACCESS_KEY_ID",
        "GSD_S3_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError):
        _ = S3Config.from_env()


def test_s3_client_put_bytes_sets_cache_control_and_optional_sse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, object]] = []

    class FakeS3:
        def put_object(self, **kwargs: object) -> None:  # noqa: ANN003
            captured.append(dict(kwargs))

    monkeypatch.setattr(S3Client, "_create_client", staticmethod(lambda _cfg: FakeS3()))

    base = dict(
        endpoint_url="http://s3.test",
        bucket="b",
        region="us-east-1",
        access_key_id="ak",
        secret_access_key="sk",
    )

    sse = S3Client(config=S3Config(**base, sse_mode="sse_s3"))
    sse.put_bytes(key="k", body=b"x", content_type="text/plain")

    none = S3Client(config=S3Config(**base, sse_mode="none"))
    none.put_bytes(key="k2", body=b"y", content_type="text/plain")

    assert captured[0]["CacheControl"] == "no-store"
    assert captured[0]["ServerSideEncryption"] == "AES256"
    assert captured[1]["CacheControl"] == "no-store"
    assert "ServerSideEncryption" not in captured[1]


def test_s3_client_presign_get_rejects_ttl_over_max(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeS3:
        def generate_presigned_url(self, *_args: object, **_kwargs: object) -> str:
            return "http://example.test/presigned"

    monkeypatch.setattr(S3Client, "_create_client", staticmethod(lambda _cfg: FakeS3()))
    client = S3Client(
        config=S3Config(
            endpoint_url="http://s3.test",
            bucket="b",
            region="us-east-1",
            access_key_id="ak",
            secret_access_key="sk",
            sse_mode="none",
        )
    )

    with pytest.raises(RuntimeError):
        _ = client.presign_get(key="k", ttl_s=3601)
