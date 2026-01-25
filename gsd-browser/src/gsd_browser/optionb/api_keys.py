from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from hmac import compare_digest
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .identity import Identity, identity_from_claims


class ApiKeyRegistryEntry(BaseModel):
    """Single API key mapping entry per HTTP_API.md contract."""

    tenant_id: str
    subject_id: str
    scopes: list[str] = Field(default_factory=list)
    key: str | None = None
    key_sha256: str | None = None
    label: str | None = None
    created_at: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_key_fields(self) -> ApiKeyRegistryEntry:
        self.key = self.key.strip() if isinstance(self.key, str) else None
        if self.key == "":
            self.key = None

        self.key_sha256 = self.key_sha256.strip() if isinstance(self.key_sha256, str) else None
        if self.key_sha256 == "":
            self.key_sha256 = None

        has_plaintext = self.key is not None
        has_sha256 = self.key_sha256 is not None

        if has_plaintext == has_sha256:
            raise ValueError("Exactly one of 'key' or 'key_sha256' must be provided")

        if has_sha256:
            _parse_key_sha256(self.key_sha256)

        self.scopes = [scope.strip() for scope in self.scopes if scope.strip()]
        return self


class ApiKeyRegistryError(ValueError):
    """Raised when the API key registry cannot be loaded or validated."""


@dataclass(frozen=True, slots=True)
class _KeyDigest:
    """Hashable wrapper that compares digests using constant-time equality."""

    digest: bytes
    _hash: int

    def __init__(self, digest: bytes) -> None:
        if not isinstance(digest, (bytes, bytearray)):
            raise TypeError("digest must be bytes")
        digest_bytes = bytes(digest)
        if len(digest_bytes) != 32:
            raise ValueError("SHA-256 digest must be 32 bytes")
        object.__setattr__(self, "digest", digest_bytes)
        object.__setattr__(self, "_hash", hash(digest_bytes))

    def __hash__(self) -> int:  # noqa: D401
        return self._hash

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _KeyDigest):
            return NotImplemented
        return compare_digest(self.digest, other.digest)


@dataclass(frozen=True, slots=True)
class ApiKeyRegistryRecord:
    identity: Identity
    scopes: frozenset[str]
    label: str | None
    created_at: str | None


@dataclass(frozen=True, slots=True)
class ApiKeyRegistry:
    _records_by_digest: dict[_KeyDigest, ApiKeyRegistryRecord]

    def lookup_identity_and_scopes(self, api_key: str) -> tuple[Identity, set[str]] | None:
        key = str(api_key or "").strip()
        if not key:
            return None
        digest = _KeyDigest(hashlib.sha256(key.encode("utf-8")).digest())
        record = self._records_by_digest.get(digest)
        if record is None:
            return None
        return record.identity, set(record.scopes)


def load_api_key_registry_from_env() -> ApiKeyRegistry | None:
    path = str(os.environ.get("GSD_API_KEYS_FILE", "")).strip()
    if not path:
        return None
    return load_api_key_registry(path)


def load_api_key_registry(path: str | Path) -> ApiKeyRegistry:
    path_obj = Path(path)
    raw = path_obj.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        raise ApiKeyRegistryError(f"Invalid JSON in API key registry: {path_obj}") from exc

    if not isinstance(payload, list):
        raise ApiKeyRegistryError("API key registry must be a JSON array of entries")

    records: dict[_KeyDigest, ApiKeyRegistryRecord] = {}
    for idx, entry_raw in enumerate(payload):
        try:
            entry = ApiKeyRegistryEntry.model_validate(entry_raw)
        except ValidationError as exc:
            raise ApiKeyRegistryError(f"Invalid API key registry entry at index {idx}") from exc

        digest_bytes = _digest_bytes_for_entry(entry)
        digest = _KeyDigest(digest_bytes)

        if digest in records:
            raise ApiKeyRegistryError(
                "Duplicate API key detected (duplicate plaintext key or key_sha256)"
            )

        identity = identity_from_claims(
            {"tenant_id": entry.tenant_id, "subject_id": entry.subject_id},
            tenant_id_claim="tenant_id",
            subject_id_claim="subject_id",
        )
        scopes = frozenset(entry.scopes)
        records[digest] = ApiKeyRegistryRecord(
            identity=identity,
            scopes=scopes,
            label=entry.label,
            created_at=entry.created_at,
        )

    return ApiKeyRegistry(records)


def _digest_bytes_for_entry(entry: ApiKeyRegistryEntry) -> bytes:
    if entry.key is not None:
        return hashlib.sha256(entry.key.encode("utf-8")).digest()
    if entry.key_sha256 is not None:
        return _parse_key_sha256(entry.key_sha256)
    raise ApiKeyRegistryError("Invalid registry entry: missing key material")


def _parse_key_sha256(value: str) -> bytes:
    try:
        digest = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError("key_sha256 must be a hex SHA-256 digest") from exc
    if len(digest) != 32:
        raise ValueError("key_sha256 must be a 64-char hex SHA-256 digest")
    return digest
