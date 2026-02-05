from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass

import fastmcp
import pytest
from fastmcp import Client
from mcp.types import ImageContent, TextContent

from gsd_browser import mcp_server as sdk_server
from gsd_browser.optionb.fastmcp_server import GsdFastMCP
from gsd_browser.optionb.identity import Identity
from gsd_browser.optionb.screenshot_artifacts import persist_screenshot


def _configure_memory_docket(monkeypatch: pytest.MonkeyPatch, *, label: str) -> None:
    monkeypatch.setattr(fastmcp.settings.docket, "url", f"memory://{label}")
    monkeypatch.setattr(fastmcp.settings.docket, "name", f"gsd-{label}")


def _configure_fake_s3_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set all required S3 env vars so has_complete_s3_config() returns True."""
    monkeypatch.setenv("GSD_S3_ENDPOINT_URL", "http://example.invalid")
    monkeypatch.setenv("GSD_S3_BUCKET", "test-bucket")
    monkeypatch.setenv("GSD_S3_REGION", "us-east-1")
    monkeypatch.setenv("GSD_S3_ACCESS_KEY_ID", "test-key")
    monkeypatch.setenv("GSD_S3_SECRET_ACCESS_KEY", "test-secret")


@dataclass(frozen=True, slots=True)
class _FakeS3:
    bucket: str
    _objects: dict[str, bytes]

    def put_bytes(self, *, key: str, body: bytes, content_type: str) -> None:  # noqa: ARG002
        self._objects[str(key)] = bytes(body)

    def get_bytes(self, *, key: str) -> bytes:
        return bytes(self._objects.get(str(key), b""))

    def presign_get(self, *, key: str, ttl_s: int) -> tuple[str, float]:
        return f"https://example.test/{key}", float(time.time() + int(ttl_s))


@pytest.mark.parametrize(
    ("delivery_mode", "include_images", "expect_inline", "expect_presigned"),
    [
        ("inline", True, True, False),
        ("inline", False, False, False),
        ("presigned", True, False, True),
        ("presigned", False, False, True),
        ("both", True, True, True),
        ("both", False, False, True),
    ],
)
def test_get_screenshots_delivery_mode_matrix(
    monkeypatch: pytest.MonkeyPatch,
    delivery_mode: str,
    include_images: bool,
    expect_inline: bool,
    expect_presigned: bool,
) -> None:
    _configure_memory_docket(monkeypatch, label="screenshots-delivery-mode")
    _configure_fake_s3_env(monkeypatch)
    monkeypatch.setenv("GSD_ARTIFACT_DELIVERY_MODE", delivery_mode)
    monkeypatch.setenv("GSD_PRESIGNED_URL_TTL_S", "900")

    from gsd_browser.optionb import s3_client as s3_client_mod

    fake_s3 = _FakeS3(bucket="bucket", _objects={})
    monkeypatch.setattr(s3_client_mod, "get_s3_client", lambda: fake_s3)

    session_id = str(uuid.uuid4())
    server = GsdFastMCP("screenshots-test", tasks=True)
    server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
        tenant_id="t1",
        subject_id="s1",
        transport="stdio",
    )

    @server.tool(name="make_screenshot")
    async def make_screenshot() -> str:
        runtime = sdk_server.get_runtime()
        shot = runtime.screenshots.record_screenshot(
            screenshot_type="agent_step",
            source="test",
            image_bytes=b"hello",
            mime_type="image/png",
            session_id=session_id,
            captured_at=time.time(),
            has_error=False,
            metadata={"source": "test"},
            url="https://example.test",
            step=1,
        )
        await persist_screenshot(shot)
        return shot.id

    @server.tool(name="get_screenshots")
    async def get_screenshots_tool(
        last_n: int = 5,
        screenshot_type: str = "agent_step",
        session_id: str = "",
        from_timestamp: float | None = None,
        has_error: bool | None = None,
        include_images: bool = True,
        ctx: object | None = None,
    ):
        return await sdk_server.get_screenshots(
            last_n=last_n,
            screenshot_type=screenshot_type,
            session_id=session_id,
            from_timestamp=from_timestamp,
            has_error=has_error,
            include_images=include_images,
            ctx=ctx,  # type: ignore[arg-type]
        )

    async def run() -> None:
        async with Client(server) as client:
            _ = await client.call_tool("make_screenshot", {})
            result = await client.call_tool_mcp(
                name="get_screenshots",
                arguments={
                    "session_id": session_id,
                    "last_n": 5,
                    "screenshot_type": "agent_step",
                    "include_images": include_images,
                },
            )
            assert result.isError is False
            assert result.content

            header = result.content[0]
            assert isinstance(header, TextContent)
            payload = json.loads(header.text)

            assert payload["session_id"] == session_id
            assert payload["error"] is None
            assert len(payload["screenshots"]) == 1

            shot = payload["screenshots"][0]
            assert shot["artifact"]["key"] == shot["id"]

            inline_included = bool(shot["inline_included"])
            artifact_url = shot["artifact"]["url"]

            assert inline_included is expect_inline
            assert (artifact_url is not None) is expect_presigned

            image_blocks = [
                entry for entry in result.content[1:] if isinstance(entry, ImageContent)
            ]
            assert len(image_blocks) == (1 if expect_inline else 0)

    asyncio.run(run())


def test_get_screenshots_is_non_enumerable_across_tenants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="screenshots-non-enumerable")
    _configure_fake_s3_env(monkeypatch)
    monkeypatch.setenv("GSD_ARTIFACT_DELIVERY_MODE", "inline")

    from gsd_browser.optionb import s3_client as s3_client_mod

    fake_s3 = _FakeS3(bucket="bucket", _objects={})
    monkeypatch.setattr(s3_client_mod, "get_s3_client", lambda: fake_s3)

    session_id = str(uuid.uuid4())
    server = GsdFastMCP("screenshots-test", tasks=True)

    @server.tool(name="make_screenshot")
    async def make_screenshot() -> str:
        runtime = sdk_server.get_runtime()
        shot = runtime.screenshots.record_screenshot(
            screenshot_type="agent_step",
            source="test",
            image_bytes=b"hello",
            mime_type="image/png",
            session_id=session_id,
            captured_at=time.time(),
            has_error=False,
            metadata={"source": "test"},
            url="https://example.test",
            step=1,
        )
        await persist_screenshot(shot)
        return shot.id

    @server.tool(name="get_screenshots")
    async def get_screenshots_tool(
        last_n: int = 5,
        screenshot_type: str = "agent_step",
        session_id: str = "",
        from_timestamp: float | None = None,
        has_error: bool | None = None,
        include_images: bool = True,
        ctx: object | None = None,
    ):
        return await sdk_server.get_screenshots(
            last_n=last_n,
            screenshot_type=screenshot_type,
            session_id=session_id,
            from_timestamp=from_timestamp,
            has_error=has_error,
            include_images=include_images,
            ctx=ctx,  # type: ignore[arg-type]
        )

    async def run() -> None:
        server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
            tenant_id="t1",
            subject_id="s1",
            transport="stdio",
        )
        async with Client(server) as client:
            _ = await client.call_tool("make_screenshot", {})

            server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
                tenant_id="t2",
                subject_id="s2",
                transport="stdio",
            )
            result = await client.call_tool_mcp(
                name="get_screenshots",
                arguments={
                    "session_id": session_id,
                    "last_n": 5,
                    "screenshot_type": "agent_step",
                    "include_images": True,
                },
            )
            assert result.isError is False
            header = result.content[0]
            assert isinstance(header, TextContent)
            payload = json.loads(header.text)
            assert payload["session_id"] == session_id
            assert payload["error"] is None
            assert payload["screenshots"] == []

    asyncio.run(run())


def test_get_screenshots_uses_distributed_store_without_s3_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="screenshots-no-s3-env")
    monkeypatch.setenv("GSD_ARTIFACT_DELIVERY_MODE", "inline")

    for name in (
        "GSD_S3_ENDPOINT_URL",
        "GSD_S3_BUCKET",
        "GSD_S3_REGION",
        "GSD_S3_ACCESS_KEY_ID",
        "GSD_S3_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    session_id = str(uuid.uuid4())
    server = GsdFastMCP("screenshots-no-s3-env", tasks=True)
    server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
        tenant_id="t1",
        subject_id="s1",
        transport="stdio",
    )

    @server.tool(name="persist_only")
    async def persist_only() -> str:
        from gsd_browser.screenshot_manager import Screenshot

        artifact_id = str(uuid.uuid4())
        shot = Screenshot(
            id=artifact_id,
            timestamp=time.time(),
            screenshot_type="agent_step",
            source="test",
            session_id=session_id,
            has_error=False,
            metadata={"source": "test"},
            image_bytes=b"hello",
            mime_type="image/png",
            url="https://example.test",
            step=1,
        )
        await persist_screenshot(shot)
        return artifact_id

    @server.tool(name="get_screenshots")
    async def get_screenshots_tool(  # noqa: D401
        last_n: int = 5,
        screenshot_type: str = "agent_step",
        session_id: str = "",
        from_timestamp: float | None = None,
        has_error: bool | None = None,
        include_images: bool = True,
        ctx: object | None = None,
    ):
        return await sdk_server.get_screenshots(
            last_n=last_n,
            screenshot_type=screenshot_type,
            session_id=session_id,
            from_timestamp=from_timestamp,
            has_error=has_error,
            include_images=include_images,
            ctx=ctx,  # type: ignore[arg-type]
        )

    async def run() -> None:
        async with Client(server) as client:
            _ = await client.call_tool("persist_only", {})
            result = await client.call_tool_mcp(
                name="get_screenshots",
                arguments={
                    "session_id": session_id,
                    "last_n": 5,
                    "screenshot_type": "agent_step",
                    "include_images": True,
                },
            )
            assert result.isError is False
            assert result.content

            header = result.content[0]
            assert isinstance(header, TextContent)
            payload = json.loads(header.text)
            assert payload["session_id"] == session_id
            assert payload["error"] is None
            assert len(payload["screenshots"]) == 1

            shot = payload["screenshots"][0]
            assert shot["inline_included"] is True

            image_blocks = [
                entry for entry in result.content[1:] if isinstance(entry, ImageContent)
            ]
            assert len(image_blocks) == 1

    asyncio.run(run())


def test_get_screenshots_supports_azure_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_memory_docket(monkeypatch, label="screenshots-azure-backend")
    monkeypatch.setenv("GSD_AZURE_STORAGE_ACCOUNT", "testacct")
    monkeypatch.setenv("GSD_AZURE_BLOB_CONTAINER", "gsd-artifacts")
    monkeypatch.setenv("GSD_ARTIFACT_DELIVERY_MODE", "both")
    monkeypatch.setenv("GSD_PRESIGNED_URL_TTL_S", "900")

    @dataclass(frozen=True, slots=True)
    class _FakeAzureBlob:
        storage_account_name: str
        container_name: str
        _objects: dict[str, bytes]

        def put_bytes(self, *, blob_name: str, body: bytes, content_type: str) -> None:  # noqa: ARG002
            self._objects[str(blob_name)] = bytes(body)

        def get_bytes(self, *, blob_name: str) -> bytes:
            return bytes(self._objects.get(str(blob_name), b""))

        def generate_sas_url(self, *, blob_name: str, ttl_s: int) -> tuple[str, float]:
            return (
                f"https://{self.storage_account_name}.blob.core.windows.net/"
                f"{self.container_name}/{blob_name}?sig=fake&ttl={int(ttl_s)}",
                float(time.time() + int(ttl_s)),
            )

    from gsd_browser.optionb import azure_blob_client as azure_blob_mod

    fake_azure = _FakeAzureBlob(
        storage_account_name="testacct",
        container_name="gsd-artifacts",
        _objects={},
    )
    monkeypatch.setattr(azure_blob_mod, "get_azure_blob_client", lambda: fake_azure)

    session_id = str(uuid.uuid4())
    server = GsdFastMCP("screenshots-azure-backend", tasks=True)
    server._resolve_identity_for_current_request = lambda: Identity(  # type: ignore[method-assign]
        tenant_id="t1",
        subject_id="s1",
        transport="stdio",
    )

    @server.tool(name="persist_only")
    async def persist_only() -> str:
        from gsd_browser.screenshot_manager import Screenshot

        artifact_id = str(uuid.uuid4())
        shot = Screenshot(
            id=artifact_id,
            timestamp=time.time(),
            screenshot_type="agent_step",
            source="test",
            session_id=session_id,
            has_error=False,
            metadata={"source": "test"},
            image_bytes=b"hello",
            mime_type="image/png",
            url="https://example.test",
            step=1,
        )
        await persist_screenshot(shot)
        return artifact_id

    @server.tool(name="get_screenshots")
    async def get_screenshots_tool(  # noqa: D401
        last_n: int = 5,
        screenshot_type: str = "agent_step",
        session_id: str = "",
        from_timestamp: float | None = None,
        has_error: bool | None = None,
        include_images: bool = True,
        ctx: object | None = None,
    ):
        return await sdk_server.get_screenshots(
            last_n=last_n,
            screenshot_type=screenshot_type,
            session_id=session_id,
            from_timestamp=from_timestamp,
            has_error=has_error,
            include_images=include_images,
            ctx=ctx,  # type: ignore[arg-type]
        )

    async def run() -> None:
        async with Client(server) as client:
            _ = await client.call_tool("persist_only", {})
            result = await client.call_tool_mcp(
                name="get_screenshots",
                arguments={
                    "session_id": session_id,
                    "last_n": 5,
                    "screenshot_type": "agent_step",
                    "include_images": True,
                },
            )
            assert result.isError is False
            assert result.content

            header = result.content[0]
            assert isinstance(header, TextContent)
            payload = json.loads(header.text)
            assert payload["session_id"] == session_id
            assert payload["error"] is None
            assert len(payload["screenshots"]) == 1

            shot = payload["screenshots"][0]
            assert shot["inline_included"] is True
            assert isinstance(shot["artifact"]["url"], str)
            assert shot["artifact"]["url"].startswith("https://testacct.blob.core.windows.net/")
            assert shot["artifact"]["url_expires_at"] is not None

            image_blocks = [
                entry for entry in result.content[1:] if isinstance(entry, ImageContent)
            ]
            assert len(image_blocks) == 1

    asyncio.run(run())
