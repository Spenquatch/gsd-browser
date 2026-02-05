from __future__ import annotations


def normalize_base_path(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return "/"

    if not raw.startswith("/"):
        raw = f"/{raw}"

    while raw != "/" and raw.endswith("/"):
        raw = raw[:-1]

    return raw


def detect_base_path(env_base_path: str | None, x_forwarded_prefix: str | None) -> str:
    if env_base_path and env_base_path.strip():
        return normalize_base_path(env_base_path)

    if x_forwarded_prefix and x_forwarded_prefix.strip():
        first = x_forwarded_prefix.split(",", 1)[0]
        return normalize_base_path(first)

    return "/"

