"""Legacy `gsd-browser` CLI shim.

This module keeps the historical command surface stable while nudging users towards `gsd`.
"""

from __future__ import annotations

import sys
from typing import Final

import click
import typer
from typer.main import get_command

from . import cli as legacy_cli_mod

_LEGACY_COMMAND: Final[click.Command] = get_command(legacy_cli_mod.app)

_PASSTHROUGH_ARG = typer.Argument(
    None,
    metavar="[ARGS]...",
    help="(internal) Forwarded to the legacy CLI unchanged.",
)

_LEGACY_TO_CANONICAL: Final[dict[str, list[str]]] = {
    "serve": ["gsd", "mcp", "serve"],
    "mcp-config": ["gsd", "mcp", "config"],
    "mcp-config-add": ["gsd", "mcp", "add"],
    "mcp-tool-smoke": ["gsd", "mcp", "smoke"],
    "list-tools": ["gsd", "mcp", "tools", "list"],
    "mcp-tools": ["gsd", "mcp", "tools"],
    "init-env": ["gsd", "config", "init"],
    "configure": ["gsd", "config", "set"],
    "ensure-browser": ["gsd", "browser", "ensure"],
    "serve-browser": ["gsd", "stream", "serve"],
    "validate-llm": ["gsd", "llm", "validate"],
    "diagnose": ["gsd", "dev", "diagnose"],
    "serve-echo": ["gsd", "dev", "echo"],
    "smoke": ["gsd", "dev", "smoke"],
}


def _replacement_for_argv(argv: list[str]) -> str:
    cmd_index = next((i for i, arg in enumerate(argv) if arg and not arg.startswith("-")), None)
    if cmd_index is None:
        if "--version" in argv:
            return "gsd --version"
        if "--help" in argv or "-h" in argv:
            return "gsd --help"
        return "gsd --help"

    command = argv[cmd_index]
    canonical_prefix = _LEGACY_TO_CANONICAL.get(command)
    if canonical_prefix is None:
        return "gsd --help"

    remainder = argv[cmd_index + 1 :]
    return " ".join([*canonical_prefix, *remainder])


def _run_legacy(argv: list[str]) -> None:
    try:
        _LEGACY_COMMAND.main(args=argv, prog_name="gsd-browser", standalone_mode=False)
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
    ctx: typer.Context,
    _passthrough: list[str] = _PASSTHROUGH_ARG,
) -> None:
    argv = list(sys.argv[1:])
    replacement = _replacement_for_argv(argv)
    typer.echo(f"Deprecated: use '{replacement}'", err=True)

    # Delegate to the original CLI to preserve behavior and exit codes.
    _run_legacy(argv)
