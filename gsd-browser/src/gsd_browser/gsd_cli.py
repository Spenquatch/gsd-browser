"""Canonical `gsd` CLI entry point.

This file intentionally starts small and grows as tasks in `tasks.json` are completed.
"""

from __future__ import annotations

import typer
from rich.console import Console

from . import __version__
from .cli import serve as legacy_serve

console = Console()

app = typer.Typer(help="GSD CLI", add_completion=False, invoke_without_command=True)
mcp_app = typer.Typer(help="MCP server commands", add_completion=False)
app.add_typer(mcp_app, name="mcp")


@app.callback()
def _root(
    version: bool = typer.Option(False, "--version", help="Print version and exit"),
) -> None:
    if version:
        # Keep output identical to the legacy `gsd-browser --version` for now.
        console.print(f"gsd-browser v{__version__}")
        raise typer.Exit()


@mcp_app.command("serve")
def mcp_serve(
    _unused_disable_echo: bool = typer.Option(
        False,
        "--no-echo",
        is_flag=True,
        help="(deprecated) Placeholder echo mode is now `serve-echo`",
        hidden=True,
    ),
    _unused_once: bool = typer.Option(
        False,
        "--once",
        is_flag=True,
        help="(deprecated) Placeholder echo mode is now `serve-echo --once`",
        hidden=True,
    ),
    log_level: str | None = typer.Option(
        None, "--log-level", help="Override log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    ),
    json_logs: bool = typer.Option(
        False, "--json-logs", is_flag=True, help="Emit structured JSON logs"
    ),
    text_logs: bool = typer.Option(
        False, "--text-logs", is_flag=True, help="Force human-friendly logs"
    ),
    llm_provider: str | None = typer.Option(
        None,
        "--llm-provider",
        help="LLM provider (anthropic, chatbrowseruse, openai, ollama)",
    ),
    llm_model: str | None = typer.Option(None, "--llm-model", help="Override LLM model name"),
    ollama_host: str | None = typer.Option(None, "--ollama-host", help="Override OLLAMA_HOST"),
) -> None:
    """Start the FastMCP stdio server (stdout is reserved for JSON-RPC)."""

    legacy_serve(
        _unused_disable_echo=_unused_disable_echo,
        _unused_once=_unused_once,
        log_level=log_level,
        json_logs=json_logs,
        text_logs=text_logs,
        llm_provider=llm_provider,
        llm_model=llm_model,
        ollama_host=ollama_host,
    )
