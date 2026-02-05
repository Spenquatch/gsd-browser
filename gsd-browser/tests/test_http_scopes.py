from __future__ import annotations

from gsd_browser.optionb.scopes import extract_scopes_from_claims, has_any_scope


def test_extract_scopes_from_claims_prefers_scope_string() -> None:
    claims = {"scope": "gsd:admin  gsd:browser:read"}
    assert extract_scopes_from_claims(claims) == {"gsd:admin", "gsd:browser:read"}


def test_extract_scopes_from_claims_scope_wrong_type_yields_empty_even_if_scp_present() -> None:
    claims = {"scope": ["gsd:admin"], "scp": ["gsd:admin"]}
    assert extract_scopes_from_claims(claims) == set()


def test_extract_scopes_from_claims_falls_back_to_scp_string() -> None:
    claims = {"scp": "gsd:browser:execute gsd:browser:read"}
    assert extract_scopes_from_claims(claims) == {"gsd:browser:execute", "gsd:browser:read"}


def test_extract_scopes_from_claims_falls_back_to_scp_list() -> None:
    claims = {"scp": ["gsd:browser:execute", "gsd:browser:read"]}
    assert extract_scopes_from_claims(claims) == {"gsd:browser:execute", "gsd:browser:read"}


def test_extract_scopes_from_claims_scp_list_with_non_string_yields_empty() -> None:
    claims = {"scp": ["gsd:admin", 123]}
    assert extract_scopes_from_claims(claims) == set()


def test_extract_scopes_from_claims_falls_back_to_clerk_org_permissions_list() -> None:
    claims = {"org_permissions": ["gsd:browser:read", "gsd:browser:execute"]}
    assert extract_scopes_from_claims(claims) == {"gsd:browser:read", "gsd:browser:execute"}


def test_extract_scopes_from_claims_org_permissions_list_with_non_string_yields_empty() -> None:
    claims = {"org_permissions": ["gsd:admin", 123]}
    assert extract_scopes_from_claims(claims) == set()


def test_has_any_scope_allows_when_required_empty() -> None:
    assert has_any_scope({"gsd:admin"}, set()) is True


def test_has_any_scope_checks_intersection() -> None:
    assert has_any_scope({"gsd:browser:read"}, {"gsd:browser:execute"}) is False
    assert has_any_scope({"gsd:browser:read"}, {"gsd:browser:read"}) is True
