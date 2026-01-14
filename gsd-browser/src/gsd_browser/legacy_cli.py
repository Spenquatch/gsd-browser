"""Legacy `gsd-browser` CLI shim.

This module keeps the historical command surface stable while nudging users towards `gsd`.
"""

from __future__ import annotations

from typing import Final

import click
import typer
from typer.main import get_command

from . import cli as legacy_cli_mod
from . import gsd_cli as canonical_cli_mod

_LEGACY_COMMAND: Final[click.Command] = get_command(legacy_cli_mod.app)
_CANONICAL_COMMAND: Final[click.Command] = get_command(canonical_cli_mod.app)

_PASSTHROUGH_ARG = typer.Argument(
    None,
    metavar="[ARGS]...",
    help="(internal) Forwarded to the legacy CLI unchanged.",
)

_LEGACY_ARGV_PREFIX_MAP: Final[dict[tuple[str, ...], tuple[str, ...]]] = {
    ("serve",): ("mcp", "serve"),
    ("mcp-config",): ("mcp", "config"),
    ("mcp-config-add",): ("mcp", "add"),
    ("mcp-tool-smoke",): ("mcp", "smoke"),
    ("list-tools",): ("mcp", "tools", "list"),
    ("mcp-tools",): ("mcp", "tools"),
    ("mcp-tools", "list"): ("mcp", "tools", "list"),
    ("mcp-tools", "enable"): ("mcp", "tools", "enable"),
    ("mcp-tools", "disable"): ("mcp", "tools", "disable"),
    ("mcp-tools", "set-enabled"): ("mcp", "tools", "allow"),
    ("mcp-tools", "set-disabled"): ("mcp", "tools", "deny"),
    ("mcp-tools", "reset"): ("mcp", "tools", "reset"),
    ("init-env",): ("config", "init"),
    ("configure",): ("config", "set"),
    ("ensure-browser",): ("browser", "ensure"),
    ("serve-browser",): ("stream", "serve"),
    ("validate-llm",): ("llm", "validate"),
    ("diagnose",): ("dev", "diagnose"),
    ("serve-echo",): ("dev", "echo"),
    ("smoke",): ("dev", "smoke"),
}

def _find_mapped_prefix(argv: list[str]) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    if not argv:
        return None

    max_prefix_len = max(len(k) for k in _LEGACY_ARGV_PREFIX_MAP)
    for length in range(max_prefix_len, 0, -1):
        key = tuple(argv[:length])
        canonical_prefix = _LEGACY_ARGV_PREFIX_MAP.get(key)
        if canonical_prefix is not None:
            return key, canonical_prefix

    return None


def _replacement_for_argv(argv: list[str]) -> str:
    cmd_index = next((i for i, arg in enumerate(argv) if arg and not arg.startswith("-")), None)
    if cmd_index is None:
        if "--version" in argv:
            return "gsd --version"
        if "--help" in argv or "-h" in argv:
            return "gsd --help"
        return "gsd --help"

    if cmd_index != 0:
        return "gsd --help"

    max_prefix_len = max(len(k) for k in _LEGACY_ARGV_PREFIX_MAP)
    mapped_key: tuple[str, ...] | None = None
    for length in range(max_prefix_len, 0, -1):
        key = tuple(argv[:length])
        if key in _LEGACY_ARGV_PREFIX_MAP:
            mapped_key = key
            break

    if mapped_key is None:
        return "gsd --help"

    canonical_prefix = _LEGACY_ARGV_PREFIX_MAP[mapped_key]
    remainder = argv[len(mapped_key) :]
    return " ".join(["gsd", *canonical_prefix, *remainder])


def _run_legacy(argv: list[str]) -> None:
    try:
        _LEGACY_COMMAND.main(args=argv, prog_name="gsd-browser", standalone_mode=False)
    except click.exceptions.Exit as exc:
        raise typer.Exit(code=exc.exit_code) from None
    except click.exceptions.Abort:
        raise typer.Exit(code=1) from None


def _run_canonical(argv: list[str]) -> None:
    try:
        _CANONICAL_COMMAND.main(args=argv, prog_name="gsd", standalone_mode=False)
    except click.exceptions.Exit as exc:
        raise typer.Exit(code=exc.exit_code) from None
    except click.exceptions.Abort:
        raise typer.Exit(code=1) from None


app = typer.Typer(
    help="Deprecated: use `gsd` instead of `gsd-browser`.",
    add_completion=False,
    add_help_option=False,
    invoke_without_command=True,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)


@app.callback()
def _callback(
    _ctx: typer.Context,
    _passthrough: list[str] = _PASSTHROUGH_ARG,
) -> None:
    argv = list(_passthrough or [])
    replacement = _replacement_for_argv(argv)
    typer.echo(f"Deprecated: use '{replacement}'", err=True)

    # Prefer canonical implementations when a mapping exists; otherwise fall back to the legacy CLI.
    mapped = _find_mapped_prefix(argv)
    if mapped is not None:
        legacy_prefix, canonical_prefix = mapped
        remainder = argv[len(legacy_prefix) :]
        _run_canonical([*canonical_prefix, *remainder])
        return

    _run_legacy(argv)
