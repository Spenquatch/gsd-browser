"""Typer CLI entry point for the MCP template."""

from __future__ import annotations

import typer
from rich.console import Console

from . import __version__
from .config import load_settings
from .logging_utils import setup_logging
from .main import serve_stdio

console = Console()
app = typer.Typer(help="Reusable MCP template utility CLI")


@app.callback()
def callback(
    version: bool = typer.Option(False, "--version", help="Print version and exit"),
) -> None:
    """Base callback for global options."""
    if version:
        console.print(f"mcp-template v{__version__}")
        raise typer.Exit()


@app.command()
def serve(
    disable_echo: bool = typer.Option(
        False, "--no-echo", is_flag=True, help="Disable echoing stdin back to stdout"
    ),
    once: bool = typer.Option(
        False, "--once", is_flag=True, help="Process a single message then exit"
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
) -> None:
    """Start the placeholder stdio MCP server."""
    settings = load_settings()

    desired_level = log_level or settings.log_level
    if json_logs and text_logs:
        console.print("[red]Cannot use --json-logs and --text-logs together[/red]")
        raise typer.Exit(code=1)
    if json_logs:
        desired_json = True
    elif text_logs:
        desired_json = False
    else:
        desired_json = settings.json_logs

    setup_logging(desired_level, json_logs=desired_json)
    console.print(
        f"[green]Config loaded[/green]: model={settings.model}, "
        f"log_level={desired_level}, json_logs={desired_json}"
    )
    serve_stdio(echo=not disable_echo, once=once)


@app.command("serve-browser")
def serve_browser(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host for the streaming server"),
    port: int = typer.Option(5009, "--port", help="Bind port for the streaming server"),
    log_level: str | None = typer.Option(
        None, "--log-level", help="Override log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    ),
    json_logs: bool = typer.Option(
        False, "--json-logs", is_flag=True, help="Emit structured JSON logs"
    ),
    text_logs: bool = typer.Option(
        False, "--text-logs", is_flag=True, help="Force human-friendly logs"
    ),
) -> None:
    """Start the browser streaming server (Socket.IO + /healthz)."""
    settings = load_settings(strict=False)

    desired_level = log_level or settings.log_level
    if json_logs and text_logs:
        console.print("[red]Cannot use --json-logs and --text-logs together[/red]")
        raise typer.Exit(code=1)
    if json_logs:
        desired_json = True
    elif text_logs:
        desired_json = False
    else:
        desired_json = settings.json_logs

    setup_logging(desired_level, json_logs=desired_json)

    from .streaming.server import run_streaming_server

    run_streaming_server(settings=settings, host=host, port=port)


@app.command()
def diagnose() -> None:
    """Run lightweight diagnostics placeholder."""
    console.print("[yellow]Diagnostics placeholder[/yellow] — detailed checks coming in T6/T7.")


@app.command()
def smoke() -> None:
    """Run placeholder smoke test."""
    console.print("[yellow]Smoke test placeholder[/yellow] — will call scripts in T6/T9.")


@app.command("mcp-config")
def mcp_config(
    format: str = typer.Option("json", "--format", help="Output format", case_sensitive=False),
) -> None:
    """Print MCP configuration snippet for the CLI."""
    settings = load_settings(strict=False)
    fmt_normalized = format.lower()
    if fmt_normalized == "toml":
        console.print(settings.to_mcp_toml())
    else:
        console.print(settings.to_mcp_snippet())


if __name__ == "__main__":
    app()
