"""Azure Blob Storage client wrapper for Option B artifacts.

This module provides a client for storing artifacts in Azure Blob Storage
using Managed Identity authentication (preferred) or connection string.

Canonical spec: `gsd-browser/docs/api/FAST_MCP_V2_CANONICAL_SPEC.md` §4.2, §4.4.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

logger = logging.getLogger("gsd_browser.optionb.azure_blob_client")


def _env(name: str) -> str:
    return str(os.environ.get(name, "")).strip()


AzureBlobAuthMode = Literal["managed_identity", "connection_string"]


@dataclass(frozen=True, slots=True)
class AzureBlobConfig:
    """Configuration for Azure Blob Storage client."""

    storage_account_name: str
    container_name: str
    auth_mode: AzureBlobAuthMode

    # Optional: connection string for auth_mode="connection_string"
    connection_string: str | None = None

    @classmethod
    def from_env(cls) -> AzureBlobConfig | None:
        """Load configuration from environment variables.

        Required env vars:
        - GSD_AZURE_STORAGE_ACCOUNT: Storage account name
        - GSD_AZURE_BLOB_CONTAINER: Container name (default: gsd-artifacts)

        Auth options (in priority order):
        1. GSD_AZURE_STORAGE_CONNECTION_STRING: Full connection string
        2. DefaultAzureCredential (Managed Identity) - no env var needed

        Returns None if required configuration is missing.
        """
        storage_account = _env("GSD_AZURE_STORAGE_ACCOUNT")
        if not storage_account:
            return None

        container_name = _env("GSD_AZURE_BLOB_CONTAINER") or "gsd-artifacts"
        connection_string = _env("GSD_AZURE_STORAGE_CONNECTION_STRING")

        if connection_string:
            return cls(
                storage_account_name=storage_account,
                container_name=container_name,
                auth_mode="connection_string",
                connection_string=connection_string,
            )

        # Default to managed identity
        return cls(
            storage_account_name=storage_account,
            container_name=container_name,
            auth_mode="managed_identity",
        )


def has_azure_blob_config() -> bool:
    """Check if Azure Blob configuration is available."""
    return bool(_env("GSD_AZURE_STORAGE_ACCOUNT"))


def is_azure_blob_endpoint(endpoint_url: str) -> bool:
    """Check if the endpoint URL is Azure Blob Storage."""
    from urllib.parse import urlparse

    parsed = urlparse(str(endpoint_url or ""))
    host = (parsed.netloc or "").lower()
    return host.endswith(".blob.core.windows.net")


class AzureBlobClient:
    """Client for Azure Blob Storage operations."""

    def __init__(self, config: AzureBlobConfig) -> None:
        self._config = config
        self._client = self._create_client(config)

    @staticmethod
    def _create_client(config: AzureBlobConfig):
        """Create Azure Blob container client based on auth mode."""
        from azure.storage.blob import ContainerClient

        if config.auth_mode == "connection_string" and config.connection_string:
            return ContainerClient.from_connection_string(
                config.connection_string,
                container_name=config.container_name,
            )

        # Managed identity using DefaultAzureCredential
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()
        account_url = f"https://{config.storage_account_name}.blob.core.windows.net"
        return ContainerClient(
            account_url=account_url,
            container_name=config.container_name,
            credential=credential,
        )

    @property
    def container_name(self) -> str:
        return self._config.container_name

    @property
    def storage_account_name(self) -> str:
        return self._config.storage_account_name

    def put_bytes(
        self,
        *,
        blob_name: str,
        body: bytes,
        content_type: str,
    ) -> None:
        """Upload bytes to a blob.

        Args:
            blob_name: Name/path of the blob
            body: Bytes to upload
            content_type: MIME type of the content
        """
        from azure.storage.blob import ContentSettings

        if not isinstance(blob_name, str) or not blob_name.strip():
            raise ValueError("blob_name is required")

        self._client.upload_blob(
            name=blob_name,
            data=body,
            overwrite=True,
            content_settings=ContentSettings(
                content_type=content_type,
                cache_control="no-store",
            ),
        )

    def get_bytes(self, *, blob_name: str) -> bytes:
        """Download blob content as bytes.

        Args:
            blob_name: Name/path of the blob

        Returns:
            Blob content as bytes
        """
        blob_client = self._client.get_blob_client(blob_name)
        downloader = blob_client.download_blob()
        return downloader.readall()

    def head(self, *, blob_name: str) -> dict[str, object]:
        """Get blob properties/metadata.

        Args:
            blob_name: Name/path of the blob

        Returns:
            Dictionary with blob properties
        """
        blob_client = self._client.get_blob_client(blob_name)
        props = blob_client.get_blob_properties()
        return {
            "content_type": props.content_settings.content_type,
            "size": props.size,
            "last_modified": props.last_modified,
            "etag": props.etag,
        }

    def delete(self, *, blob_name: str) -> None:
        """Delete a blob.

        Args:
            blob_name: Name/path of the blob
        """
        from azure.core.exceptions import ResourceNotFoundError

        blob_client = self._client.get_blob_client(blob_name)
        try:
            blob_client.delete_blob()
        except ResourceNotFoundError:
            pass  # Already deleted or never existed

    def generate_sas_url(self, *, blob_name: str, ttl_s: int) -> tuple[str, float]:
        """Generate a SAS URL for blob access.

        For Managed Identity: Uses user delegation key to generate SAS.
        For Connection String: Uses account key to generate SAS.

        Args:
            blob_name: Name/path of the blob
            ttl_s: Time-to-live in seconds (max 3600)

        Returns:
            Tuple of (SAS URL, expiry timestamp)
        """
        from datetime import UTC, datetime

        from azure.storage.blob import BlobSasPermissions, generate_blob_sas

        if ttl_s <= 0:
            raise ValueError("ttl_s must be > 0")
        if ttl_s > 3600:
            raise ValueError("ttl_s must be <= 3600")

        now = datetime.now(UTC)
        expiry = now + timedelta(seconds=ttl_s)
        expiry_ts = time.time() + ttl_s

        if self._config.auth_mode == "connection_string" and self._config.connection_string:
            # Extract account key from connection string
            account_key = self._extract_account_key(self._config.connection_string)
            sas_token = generate_blob_sas(
                account_name=self._config.storage_account_name,
                container_name=self._config.container_name,
                blob_name=blob_name,
                account_key=account_key,
                permission=BlobSasPermissions(read=True),
                expiry=expiry,
            )
        else:
            # Managed identity: use user delegation key
            sas_token = self._generate_user_delegation_sas(blob_name, expiry)

        blob_url = (
            f"https://{self._config.storage_account_name}.blob.core.windows.net/"
            f"{self._config.container_name}/{blob_name}?{sas_token}"
        )
        return blob_url, expiry_ts

    def _extract_account_key(self, connection_string: str) -> str:
        """Extract account key from connection string."""
        for part in connection_string.split(";"):
            if part.startswith("AccountKey="):
                return part[len("AccountKey=") :]
        raise ValueError("AccountKey not found in connection string")

    def _generate_user_delegation_sas(self, blob_name: str, expiry) -> str:
        """Generate SAS using user delegation key (for Managed Identity)."""
        from datetime import UTC, datetime

        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobSasPermissions, BlobServiceClient, generate_blob_sas

        credential = DefaultAzureCredential()
        account_url = f"https://{self._config.storage_account_name}.blob.core.windows.net"
        service_client = BlobServiceClient(account_url=account_url, credential=credential)

        # Get user delegation key (valid for same duration as SAS)
        start_time = datetime.now(UTC)
        user_delegation_key = service_client.get_user_delegation_key(
            key_start_time=start_time,
            key_expiry_time=expiry,
        )

        sas_token = generate_blob_sas(
            account_name=self._config.storage_account_name,
            container_name=self._config.container_name,
            blob_name=blob_name,
            user_delegation_key=user_delegation_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
        )
        return sas_token


# Module-level singleton
_client: AzureBlobClient | None = None


def get_azure_blob_client() -> AzureBlobClient:
    """Get or create the Azure Blob client singleton."""
    global _client
    if _client is not None:
        return _client

    config = AzureBlobConfig.from_env()
    if config is None:
        raise RuntimeError(
            "Azure Blob configuration is incomplete. "
            "Set GSD_AZURE_STORAGE_ACCOUNT and either GSD_AZURE_STORAGE_CONNECTION_STRING "
            "or configure Managed Identity."
        )

    _client = AzureBlobClient(config)
    return _client
