from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def extract_scopes_from_claims(claims: Mapping[str, Any]) -> set[str]:
    """Extract OAuth scopes from JWT claims per canonical spec.

    Rules:
    - Prefer claim `scope` (space-separated string).
    - Fallback to claim `scp` (string or list[str]).
    - Any invalid scope claim format results in an empty set.
    """

    if "scope" in claims:
        raw_scope = claims.get("scope")
        if isinstance(raw_scope, str):
            return _parse_scope_string(raw_scope)
        return set()

    raw_scp = claims.get("scp")
    if raw_scp is None:
        # Clerk (no custom JWT template) commonly provides org permissions as a list.
        # Supporting this keeps the server IdP-agnostic while allowing Clerk defaults.
        raw_org_permissions = claims.get("org_permissions")
        if isinstance(raw_org_permissions, list):
            scopes: set[str] = set()
            for item in raw_org_permissions:
                if not isinstance(item, str):
                    return set()
                scope = item.strip()
                if scope:
                    scopes.add(scope)
            return scopes
        if isinstance(raw_org_permissions, str):
            return _parse_scope_string(raw_org_permissions)
        return set()

    if isinstance(raw_scp, str):
        return _parse_scope_string(raw_scp)

    if isinstance(raw_scp, list):
        scopes: set[str] = set()
        for item in raw_scp:
            if not isinstance(item, str):
                return set()
            scope = item.strip()
            if scope:
                scopes.add(scope)
        return scopes

    return set()


def has_any_scope(scopes: set[str], required: Iterable[str]) -> bool:
    required_set = set(required)
    if not required_set:
        return True
    return bool(scopes.intersection(required_set))


def _parse_scope_string(value: str) -> set[str]:
    return {scope for scope in value.strip().split() if scope}
