"""User-level configuration file helpers.

GSD Browser supports configuration via shell environment variables and/or a .env file.
For production installs (pipx), we standardize on a stable per-user env file location:

  ~/.config/gsd-browser/.env

MCP host configs can then set GSD_BROWSER_ENV_FILE to that path so the server loads the
same credentials regardless of working directory. Shell env vars still take precedence.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_ENV_TEMPLATE = """# gsd-browser user config
#
# This file is loaded when GSD_BROWSER_ENV_FILE points here.
# Shell environment variables win over values in this file.
#
# Provider + model defaults (cost-optimized with fallback):
GSD_BROWSER_LLM_PROVIDER=anthropic
GSD_BROWSER_MODEL=claude-haiku-4-5
GSD_BROWSER_FALLBACK_LLM_PROVIDER=anthropic
GSD_BROWSER_FALLBACK_MODEL=claude-sonnet-4-5
#
# API keys (required for Anthropic/OpenAI; leave blank if you only use shell env vars):
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
#
# Optional: browser-use hosted LLM provider (if you use it)
BROWSER_USE_API_KEY=
BROWSER_USE_LLM_URL=
#
# Optional: local model provider (Ollama)
OLLAMA_HOST=http://localhost:11434
#
# Optional: pin a specific browser binary path (otherwise browser-use auto-detects)
GSD_BROWSER_BROWSER_EXECUTABLE_PATH=
"""


def default_config_dir() -> Path:
    return Path.home() / ".config" / "gsd-browser"


def default_env_path() -> Path:
    return default_config_dir() / ".env"


def ensure_env_file(*, path: Path | None = None, overwrite: bool = False) -> Path:
    env_path = path or default_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    if overwrite or not env_path.exists():
        env_path.write_text(DEFAULT_ENV_TEMPLATE, encoding="utf-8")
        try:
            env_path.chmod(0o600)
        except OSError:
            pass
    return env_path


def update_env_file(*, path: Path, updates: dict[str, str]) -> None:
    """Upsert KEY=VALUE lines in a .env file without clobbering comments."""

    if not path.exists():
        ensure_env_file(path=path, overwrite=False)

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    remaining = dict(updates)

    def _match_key(line: str) -> str | None:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            return None
        if "=" not in stripped:
            return None
        key = stripped.split("=", 1)[0].strip()
        return key if key in remaining else None

    out: list[str] = []
    for line in lines:
        key = _match_key(line)
        if key is None:
            out.append(line)
            continue
        out.append(f"{key}={remaining.pop(key)}\n")

    if remaining:
        if out and not out[-1].endswith("\n"):
            out[-1] = f"{out[-1]}\n"
        out.append("\n# Added by gsd-browser\n")
        for key, value in sorted(remaining.items()):
            out.append(f"{key}={value}\n")

    path.write_text("".join(out), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
