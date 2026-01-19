"""S3-compatible client wrapper for Option B artifacts.

Canonical spec: `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` §4.2, §4.4, §8.6.
"""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

S3SseMode = Literal["sse_s3", "none"]


def _env(name: str, env: Mapping[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    return str(source.get(name, "")).strip()


def _validate_required(value: str, *, name: str) -> str:
    raw = str(value).strip()
    if not raw:
        raise RuntimeError(f"{name} is required for Option B artifact storage")
    return raw


def _validate_endpoint_url(raw: str) -> str:
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise RuntimeError(
            f"GSD_S3_ENDPOINT_URL must be http(s) (got scheme={scheme!r}, url={raw!r})"
        )
    if not parsed.netloc:
        raise RuntimeError(f"GSD_S3_ENDPOINT_URL must include a host (url={raw!r})")
    return raw


def _validate_sse_mode(raw: str) -> S3SseMode:
    normalized = str(raw or "").strip().lower()
    if not normalized:
        return "sse_s3"
    if normalized not in {"sse_s3", "none"}:
        raise RuntimeError("GSD_S3_SSE_MODE must be 'sse_s3' or 'none'")
    return normalized  # type: ignore[return-value]


def _validate_presign_ttl_s(value: int) -> int:
    ttl_s = int(value)
    if ttl_s <= 0:
        raise RuntimeError("Presign TTL must be > 0 seconds")
    if ttl_s > 3600:
        raise RuntimeError("Presign TTL must be <= 3600 seconds")
    return ttl_s


@dataclass(frozen=True, slots=True)
class S3Config:
    endpoint_url: str
    bucket: str
    region: str
    access_key_id: str
    secret_access_key: str
    sse_mode: S3SseMode = "sse_s3"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> S3Config:
        endpoint_url = _validate_required(
            _env("GSD_S3_ENDPOINT_URL", env), name="GSD_S3_ENDPOINT_URL"
        )
        bucket = _validate_required(_env("GSD_S3_BUCKET", env), name="GSD_S3_BUCKET")
        region = _validate_required(_env("GSD_S3_REGION", env), name="GSD_S3_REGION")
        access_key_id = _validate_required(
            _env("GSD_S3_ACCESS_KEY_ID", env), name="GSD_S3_ACCESS_KEY_ID"
        )
        secret_access_key = _validate_required(
            _env("GSD_S3_SECRET_ACCESS_KEY", env), name="GSD_S3_SECRET_ACCESS_KEY"
        )
        sse_mode = _validate_sse_mode(_env("GSD_S3_SSE_MODE", env))

        endpoint_url = _validate_endpoint_url(endpoint_url)
        return cls(
            endpoint_url=endpoint_url,
            bucket=bucket,
            region=region,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            sse_mode=sse_mode,
        )


class S3Client:
    def __init__(self, *, config: S3Config) -> None:
        self._config = config
        self._client = self._create_client(config)

    @staticmethod
    def _create_client(config: S3Config):
        import boto3
        from botocore.config import Config

        session = boto3.session.Session(
            aws_access_key_id=config.access_key_id,
            aws_secret_access_key=config.secret_access_key,
            region_name=config.region,
        )
        return session.client(
            "s3",
            endpoint_url=config.endpoint_url,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    @property
    def bucket(self) -> str:
        return self._config.bucket

    def put_bytes(
        self,
        *,
        key: str,
        body: bytes,
        content_type: str,
    ) -> None:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("key is required")

        extra: dict[str, object] = {
            "Bucket": self._config.bucket,
            "Key": key,
            "Body": body,
            "ContentType": str(content_type),
            "CacheControl": "no-store",
        }
        if self._config.sse_mode == "sse_s3":
            extra["ServerSideEncryption"] = "AES256"

        self._client.put_object(**extra)

    def head(self, *, key: str) -> dict[str, object]:
        return dict(self._client.head_object(Bucket=self._config.bucket, Key=key))

    def get_bytes(self, *, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._config.bucket, Key=key)
        body = response.get("Body")
        if body is None:
            return b""
        return body.read()

    def delete(self, *, key: str) -> None:
        import botocore.exceptions

        try:
            self._client.delete_object(Bucket=self._config.bucket, Key=key)
        except botocore.exceptions.ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", "")).strip()
            if code in {"NoSuchKey", "NotFound", "404"}:
                return
            raise

    def presign_get(self, *, key: str, ttl_s: int) -> tuple[str, float]:
        ttl_value = _validate_presign_ttl_s(ttl_s)
        url = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._config.bucket, "Key": key},
            ExpiresIn=ttl_value,
            HttpMethod="GET",
        )
        return str(url), float(time.time() + ttl_value)


_client: S3Client | None = None


def get_s3_client() -> S3Client:
    global _client
    if _client is not None:
        return _client
    config = S3Config.from_env()
    _client = S3Client(config=config)
    return _client
