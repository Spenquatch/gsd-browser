from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from gsd_browser.optionb.api_keys import ApiKeyRegistryError, load_api_key_registry


def test_api_key_registry_plaintext_lookup_uses_constant_time_compare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = "super-secret-key"
    registry_path = tmp_path / "keys.json"
    registry_path.write_text(
        json.dumps(
            [
                {
                    "key": key,
                    "tenant_id": "tenant_a",
                    "subject_id": "ops_bot",
                    "scopes": ["gsd:admin"],
                }
            ]
        ),
        encoding="utf-8",
    )

    import gsd_browser.optionb.api_keys as api_keys

    calls = {"count": 0}

    def wrapped_compare_digest(a: object, b: object) -> bool:
        calls["count"] += 1
        return hmac.compare_digest(a, b)

    monkeypatch.setattr(api_keys, "compare_digest", wrapped_compare_digest)

    registry = load_api_key_registry(registry_path)
    identity, scopes = registry.lookup_identity_and_scopes(key) or (None, None)

    assert identity is not None
    assert identity.tenant_id == "tenant_a"
    assert identity.subject_id == "ops_bot"
    assert scopes == {"gsd:admin"}
    assert calls["count"] >= 1


def test_api_key_registry_sha256_lookup(tmp_path: Path) -> None:
    key = "another-secret-key"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    registry_path = tmp_path / "keys.json"
    registry_path.write_text(
        json.dumps(
            [
                {
                    "key_sha256": digest,
                    "tenant_id": "tenant_a",
                    "subject_id": "ops_bot",
                    "scopes": ["gsd:browser:read"],
                    "label": "ops-bot",
                }
            ]
        ),
        encoding="utf-8",
    )

    registry = load_api_key_registry(registry_path)
    identity, scopes = registry.lookup_identity_and_scopes(key) or (None, None)

    assert identity is not None
    assert identity.tenant_id == "tenant_a"
    assert identity.subject_id == "ops_bot"
    assert scopes == {"gsd:browser:read"}


def test_api_key_registry_invalid_json(tmp_path: Path) -> None:
    registry_path = tmp_path / "keys.json"
    registry_path.write_text("{", encoding="utf-8")
    with pytest.raises(ApiKeyRegistryError):
        load_api_key_registry(registry_path)


def test_api_key_registry_invalid_entry(tmp_path: Path) -> None:
    registry_path = tmp_path / "keys.json"
    registry_path.write_text(
        json.dumps(
            [
                {
                    "key": "abc",
                    "key_sha256": hashlib.sha256(b"abc").hexdigest(),
                    "tenant_id": "tenant_a",
                    "subject_id": "ops_bot",
                    "scopes": ["gsd:admin"],
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ApiKeyRegistryError):
        load_api_key_registry(registry_path)


def test_api_key_registry_duplicate_key_detected(tmp_path: Path) -> None:
    key = "dup-key"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    registry_path = tmp_path / "keys.json"
    registry_path.write_text(
        json.dumps(
            [
                {
                    "key": key,
                    "tenant_id": "tenant_a",
                    "subject_id": "ops_bot",
                    "scopes": ["gsd:admin"],
                },
                {
                    "key_sha256": digest,
                    "tenant_id": "tenant_a",
                    "subject_id": "ops_bot",
                    "scopes": ["gsd:admin"],
                },
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ApiKeyRegistryError):
        load_api_key_registry(registry_path)
