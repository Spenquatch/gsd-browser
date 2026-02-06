from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from gsd_browser.optionb.azure_blob_client import AzureBlobClient, AzureBlobConfig


@pytest.fixture()
def azure_sdk_stub(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[dict[str, Any]]]:
    """Stub the minimal Azure SDK surface used by AzureBlobClient.

    The production module imports Azure SDK modules lazily inside methods. These stubs
    let the unit tests run even when the Azure SDK isn't installed.
    """

    calls: dict[str, list[dict[str, Any]]] = {"generate_blob_sas": []}

    azure_mod = types.ModuleType("azure")
    storage_mod = types.ModuleType("azure.storage")
    blob_mod = types.ModuleType("azure.storage.blob")
    core_mod = types.ModuleType("azure.core")
    core_exceptions_mod = types.ModuleType("azure.core.exceptions")
    identity_mod = types.ModuleType("azure.identity")

    azure_mod.__path__ = []  # type: ignore[attr-defined]
    storage_mod.__path__ = []  # type: ignore[attr-defined]

    class ContentSettings:
        def __init__(self, *, content_type: str, cache_control: str | None = None) -> None:
            self.content_type = content_type
            self.cache_control = cache_control

    class BlobSasPermissions:
        def __init__(self, *, read: bool = False) -> None:
            self.read = read

    def generate_blob_sas(**kwargs: Any) -> str:  # noqa: ANN401
        calls["generate_blob_sas"].append(dict(kwargs))
        return "SAS_TOKEN"

    class ResourceNotFoundError(Exception):
        pass

    class DefaultAzureCredential:
        pass

    blob_mod.ContentSettings = ContentSettings
    blob_mod.BlobSasPermissions = BlobSasPermissions
    blob_mod.generate_blob_sas = generate_blob_sas

    core_exceptions_mod.ResourceNotFoundError = ResourceNotFoundError
    core_mod.exceptions = core_exceptions_mod

    identity_mod.DefaultAzureCredential = DefaultAzureCredential

    storage_mod.blob = blob_mod
    azure_mod.storage = storage_mod
    azure_mod.core = core_mod
    azure_mod.identity = identity_mod

    monkeypatch.setitem(sys.modules, "azure", azure_mod)
    monkeypatch.setitem(sys.modules, "azure.storage", storage_mod)
    monkeypatch.setitem(sys.modules, "azure.storage.blob", blob_mod)
    monkeypatch.setitem(sys.modules, "azure.core", core_mod)
    monkeypatch.setitem(sys.modules, "azure.core.exceptions", core_exceptions_mod)
    monkeypatch.setitem(sys.modules, "azure.identity", identity_mod)

    return calls


def test_put_bytes_uploads_with_content_settings(
    monkeypatch: pytest.MonkeyPatch,
    azure_sdk_stub: dict[str, list[dict[str, Any]]],  # noqa: ARG001
) -> None:
    captured: list[dict[str, Any]] = []

    class FakeContainerClient:
        def upload_blob(self, **kwargs: Any) -> None:  # noqa: ANN401
            captured.append(dict(kwargs))

    monkeypatch.setattr(
        AzureBlobClient,
        "_create_client",
        staticmethod(lambda _cfg: FakeContainerClient()),
    )

    client = AzureBlobClient(
        config=AzureBlobConfig(
            storage_account_name="acct",
            container_name="cont",
            auth_mode="managed_identity",
        )
    )

    client.put_bytes(blob_name="path/to/blob.txt", body=b"hello", content_type="text/plain")

    assert len(captured) == 1
    assert captured[0]["name"] == "path/to/blob.txt"
    assert captured[0]["data"] == b"hello"
    assert captured[0]["overwrite"] is True
    content_settings = captured[0]["content_settings"]
    assert content_settings.content_type == "text/plain"
    assert content_settings.cache_control == "no-store"


def test_get_bytes_downloads_blob_content(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeDownloader:
        def readall(self) -> bytes:
            return b"downloaded"

    class FakeBlobClient:
        def download_blob(self) -> FakeDownloader:
            return FakeDownloader()

    class FakeContainerClient:
        def __init__(self) -> None:
            self.requested_blob: str | None = None

        def get_blob_client(self, blob_name: str) -> FakeBlobClient:
            self.requested_blob = blob_name
            return FakeBlobClient()

    container = FakeContainerClient()
    monkeypatch.setattr(AzureBlobClient, "_create_client", staticmethod(lambda _cfg: container))

    client = AzureBlobClient(
        config=AzureBlobConfig(
            storage_account_name="acct",
            container_name="cont",
            auth_mode="managed_identity",
        )
    )

    body = client.get_bytes(blob_name="a/b/c.png")

    assert body == b"downloaded"
    assert container.requested_blob == "a/b/c.png"


def test_generate_sas_url_connection_string_success(
    monkeypatch: pytest.MonkeyPatch,
    azure_sdk_stub: dict[str, list[dict[str, Any]]],
) -> None:
    monkeypatch.setattr(AzureBlobClient, "_create_client", staticmethod(lambda _cfg: object()))
    monkeypatch.setattr("gsd_browser.optionb.azure_blob_client.time.time", lambda: 1000.0)

    client = AzureBlobClient(
        config=AzureBlobConfig(
            storage_account_name="acct",
            container_name="cont",
            auth_mode="connection_string",
            connection_string="AccountName=acct;AccountKey=KEY123;",
        )
    )

    url, expiry_ts = client.generate_sas_url(blob_name="x/y.txt", ttl_s=60)

    assert url == "https://acct.blob.core.windows.net/cont/x/y.txt?SAS_TOKEN"
    assert expiry_ts == 1060.0

    assert len(azure_sdk_stub["generate_blob_sas"]) == 1
    call = azure_sdk_stub["generate_blob_sas"][0]
    assert call["account_name"] == "acct"
    assert call["container_name"] == "cont"
    assert call["blob_name"] == "x/y.txt"
    assert call["account_key"] == "KEY123"
    assert call["permission"].read is True
    assert "user_delegation_key" not in call


def test_generate_sas_url_connection_string_missing_account_key_raises(
    monkeypatch: pytest.MonkeyPatch,
    azure_sdk_stub: dict[str, list[dict[str, Any]]],  # noqa: ARG001
) -> None:
    monkeypatch.setattr(AzureBlobClient, "_create_client", staticmethod(lambda _cfg: object()))

    client = AzureBlobClient(
        config=AzureBlobConfig(
            storage_account_name="acct",
            container_name="cont",
            auth_mode="connection_string",
            connection_string="AccountName=acct;",
        )
    )

    with pytest.raises(ValueError, match="AccountKey not found"):
        _ = client.generate_sas_url(blob_name="x/y.txt", ttl_s=60)


def test_generate_sas_url_managed_identity_success_uses_user_delegation_sas(
    monkeypatch: pytest.MonkeyPatch,
    azure_sdk_stub: dict[str, list[dict[str, Any]]],
) -> None:
    monkeypatch.setattr(AzureBlobClient, "_create_client", staticmethod(lambda _cfg: object()))
    monkeypatch.setattr("gsd_browser.optionb.azure_blob_client.time.time", lambda: 2000.0)

    captured: list[dict[str, Any]] = []

    def fake_generate_user_delegation_sas(
        self: AzureBlobClient,
        blob_name: str,
        expiry: Any,
    ) -> str:
        captured.append({"blob_name": blob_name, "expiry": expiry})
        return "MI_TOKEN"

    monkeypatch.setattr(
        AzureBlobClient,
        "_generate_user_delegation_sas",
        fake_generate_user_delegation_sas,
    )

    client = AzureBlobClient(
        config=AzureBlobConfig(
            storage_account_name="acct",
            container_name="cont",
            auth_mode="managed_identity",
        )
    )

    url, expiry_ts = client.generate_sas_url(blob_name="z.bin", ttl_s=30)

    assert url == "https://acct.blob.core.windows.net/cont/z.bin?MI_TOKEN"
    assert expiry_ts == 2030.0
    assert captured[0]["blob_name"] == "z.bin"
    assert len(azure_sdk_stub["generate_blob_sas"]) == 0


def test_generate_sas_url_rejects_ttl_out_of_range(
    monkeypatch: pytest.MonkeyPatch,
    azure_sdk_stub: dict[str, list[dict[str, Any]]],  # noqa: ARG001
) -> None:
    monkeypatch.setattr(AzureBlobClient, "_create_client", staticmethod(lambda _cfg: object()))

    client = AzureBlobClient(
        config=AzureBlobConfig(
            storage_account_name="acct",
            container_name="cont",
            auth_mode="managed_identity",
        )
    )

    with pytest.raises(ValueError, match="ttl_s must be > 0"):
        _ = client.generate_sas_url(blob_name="x", ttl_s=0)

    with pytest.raises(ValueError, match="ttl_s must be <= 3600"):
        _ = client.generate_sas_url(blob_name="x", ttl_s=3601)


def test_generate_sas_url_managed_identity_propagates_user_delegation_errors(
    monkeypatch: pytest.MonkeyPatch,
    azure_sdk_stub: dict[str, list[dict[str, Any]]],  # noqa: ARG001
) -> None:
    monkeypatch.setattr(AzureBlobClient, "_create_client", staticmethod(lambda _cfg: object()))

    def boom(self: AzureBlobClient, _blob_name: str, _expiry: Any) -> str:
        raise RuntimeError("delegation failed")

    monkeypatch.setattr(AzureBlobClient, "_generate_user_delegation_sas", boom)

    client = AzureBlobClient(
        config=AzureBlobConfig(
            storage_account_name="acct",
            container_name="cont",
            auth_mode="managed_identity",
        )
    )

    with pytest.raises(RuntimeError, match="delegation failed"):
        _ = client.generate_sas_url(blob_name="x", ttl_s=60)
