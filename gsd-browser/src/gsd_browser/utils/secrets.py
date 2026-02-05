"""Secret redaction utilities for safe logging and error messages.

These functions help prevent accidental exposure of credentials in logs,
error messages, and other output.
"""

from __future__ import annotations


def redact_url_password(url: str) -> str:
    """Redact embedded passwords in URLs.

    Examples:
        >>> redact_url_password("rediss://:secret@host:6380/0")
        'rediss://:****@host:6380/0'
        >>> redact_url_password("redis://user:pass@host:6379")
        'redis://user:****@host:6379'
        >>> redact_url_password("https://api.example.com/path")
        'https://api.example.com/path'

    Args:
        url: URL that may contain embedded credentials

    Returns:
        URL with password replaced by '****', or original URL if no password present
    """
    raw = str(url or "").strip()
    if not raw:
        return raw

    try:
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(raw)
        if parts.password is None:
            return raw

        hostname = parts.hostname or ""
        port = f":{parts.port}" if parts.port is not None else ""

        # Keep username if present; always redact password.
        if parts.username is not None:
            userinfo = f"{parts.username}:****@"
        else:
            # Password-only URLs like rediss://:pwd@host
            userinfo = ":****@"

        netloc = f"{userinfo}{hostname}{port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        # Best-effort string redaction if URL parsing fails.
        scheme_sep = raw.find("://")
        at = raw.find("@", scheme_sep + 3 if scheme_sep >= 0 else 0)
        if scheme_sep >= 0 and at > scheme_sep:
            return f"{raw[:scheme_sep+3]}****@{raw[at+1:]}"
        return raw


def redact_sensitive_value(value: str, visible_chars: int = 4) -> str:
    """Redact a sensitive value, showing only the first few characters.

    Examples:
        >>> redact_sensitive_value("sk-abc123xyz789")
        'sk-a****'
        >>> redact_sensitive_value("short", visible_chars=2)
        'sh****'
        >>> redact_sensitive_value("")
        ''

    Args:
        value: Sensitive value to redact
        visible_chars: Number of leading characters to keep visible

    Returns:
        Redacted value with only the first N characters visible
    """
    raw = str(value or "").strip()
    if not raw:
        return raw
    if len(raw) <= visible_chars:
        return "****"
    return f"{raw[:visible_chars]}****"


def is_url_with_password(url: str) -> bool:
    """Check if a URL contains an embedded password.

    Args:
        url: URL to check

    Returns:
        True if the URL contains a password, False otherwise
    """
    raw = str(url or "").strip()
    if not raw:
        return False
    try:
        from urllib.parse import urlsplit

        parts = urlsplit(raw)
        return parts.password is not None
    except Exception:
        # Fallback heuristic: look for :pwd@ pattern
        scheme_sep = raw.find("://")
        at = raw.find("@", scheme_sep + 3 if scheme_sep >= 0 else 0)
        return scheme_sep >= 0 and at > scheme_sep
