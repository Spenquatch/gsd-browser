from __future__ import annotations

import socket
import time
import uuid
from urllib.error import URLError
from urllib.request import urlopen

import boto3
import botocore.exceptions
import pytest
from botocore.config import Config

from gsd_browser.optionb.s3_client import S3Client, S3Config


def _is_endpoint_reachable(host: str, port: int, *, timeout_s: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _wait_for_s3_ready(client, *, timeout_s: float = 30.0) -> None:  # noqa: ANN001
    deadline = time.time() + float(timeout_s)
    last_exc: Exception | None = None
    while time.time() < deadline:
        try:
            _ = client.list_buckets()
            return
        except (
            botocore.exceptions.EndpointConnectionError,
            botocore.exceptions.ConnectionClosedError,
            botocore.exceptions.ReadTimeoutError,
            botocore.exceptions.ConnectTimeoutError,
            botocore.exceptions.SSLError,
        ) as exc:
            last_exc = exc
            time.sleep(0.5)
            continue
        except botocore.exceptions.ClientError:
            return
    raise AssertionError(f"S3 endpoint did not become ready within {timeout_s}s: {last_exc}")


@pytest.mark.integration
def test_s3_compat_smoke_seaweedfs() -> None:
    endpoint_url = "http://localhost:8333"
    host = "localhost"
    port = 8333

    if not _is_endpoint_reachable(host, port):
        pytest.skip(
            f"S3 test endpoint not reachable at {endpoint_url}. Start it with: "
            "docker compose -f docker/compose.yml -f docker/compose.s3test.yml up -d"
        )

    config = S3Config(
        endpoint_url=endpoint_url,
        bucket="gsd-s3test",
        region="us-east-1",
        access_key_id="gsd_s3test_access",
        secret_access_key="gsd_s3test_secret",
        sse_mode="none",
    )

    session = boto3.session.Session(
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        region_name=config.region,
    )
    raw = session.client(
        "s3",
        endpoint_url=config.endpoint_url,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    _wait_for_s3_ready(raw, timeout_s=30.0)
    try:
        raw.create_bucket(Bucket=config.bucket)
    except botocore.exceptions.ClientError:
        pass

    client = S3Client(config=config)

    session_id = str(uuid.uuid4())
    now_ms = int(time.time() * 1000)
    key = (
        f"tenants/t/subjects/s/sessions/{session_id}/screenshots/"
        f"{now_ms}_{uuid.uuid4()}.txt"
    )
    body = b"hello s3 compat"

    client.put_bytes(key=key, body=body, content_type="text/plain")
    head = client.head(key=key)
    assert head.get("CacheControl") == "no-store"

    url, _expires_at = client.presign_get(key=key, ttl_s=60)
    try:
        with urlopen(url, timeout=2.0) as resp:  # noqa: S310
            fetched = resp.read()
    except URLError as exc:
        raise AssertionError(f"presigned GET failed: {exc}") from exc
    assert fetched == body

    client.delete(key=key)

    with pytest.raises(botocore.exceptions.ClientError):
        _ = client.head(key=key)
