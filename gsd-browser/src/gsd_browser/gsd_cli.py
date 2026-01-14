"""Canonical `gsd` CLI entry point.

This file intentionally starts small and grows as tasks in `tasks.json` are completed.
"""

from __future__ import annotations

import os
import sys

import typer
from rich.console import Console

from . import __version__
from .cli import mcp_config_add as legacy_mcp_config_add
from .cli import mcp_tool_smoke as legacy_mcp_tool_smoke
from .cli import serve as legacy_serve
from .config import load_settings

console = Console()

app = typer.Typer(help="GSD CLI", add_completion=False, invoke_without_command=True)

mcp_app = typer.Typer(
    help="MCP server and integration",
    add_completion=False,
    epilog="Examples:\n  gsd mcp serve\n  gsd mcp --help\n",
)
config_app = typer.Typer(
    help="Stable config file lifecycle",
    add_completion=False,
    epilog="Examples:\n  gsd config --help\n  gsd config init\n",
)
browser_app = typer.Typer(
    help="Local browser/bootstrap utilities",
    add_completion=False,
    epilog="Examples:\n  gsd browser --help\n  gsd browser ensure\n",
)
stream_app = typer.Typer(
    help="Streaming server and dashboard",
    add_completion=False,
    epilog="Examples:\n  gsd stream --help\n  gsd stream serve\n",
)
llm_app = typer.Typer(
    help="LLM provider validation",
    add_completion=False,
    epilog="Examples:\n  gsd llm --help\n  gsd llm validate\n",
)
dev_app = typer.Typer(
    help="Developer/debug utilities",
    add_completion=False,
    epilog="Examples:\n  gsd dev --help\n  gsd dev diagnose\n",
)

app.add_typer(mcp_app, name="mcp")
app.add_typer(config_app, name="config")
app.add_typer(browser_app, name="browser")
app.add_typer(stream_app, name="stream")
app.add_typer(llm_app, name="llm")
app.add_typer(dev_app, name="dev")


@app.callback()
def _root(
    version: bool = typer.Option(False, "--version", help="Print version and exit"),
) -> None:
    """GSD command line interface.

    Examples:
      gsd --help
      gsd mcp --help
    """
    if version:
        # Keep output identical to the legacy `gsd-browser --version` for now.
        console.print(f"gsd-browser v{__version__}")
        raise typer.Exit()


@mcp_app.callback()
def _mcp_callback() -> None:
    """MCP server commands and host configuration.

    Examples:
      gsd mcp serve
      gsd mcp --help
    """


@mcp_app.command("config")
def mcp_config(
    format: str = typer.Option("json", "--format", help="Output format", case_sensitive=False),
    include_key_placeholders: bool = typer.Option(
        False,
        "--include-key-placeholders",
        help="Emit ${VAR} placeholders for API keys (some MCP hosts expand these; Codex does not).",
    ),
) -> None:
    """Print MCP configuration snippet for an MCP host.

    Examples:
      gsd mcp config
      gsd mcp config --format toml
    """
    settings = load_settings(strict=False)
    fmt_normalized = format.lower()
    if fmt_normalized == "toml":
        typer.echo(settings.to_mcp_toml(include_key_placeholders=include_key_placeholders))
        return
    typer.echo(settings.to_mcp_snippet(include_key_placeholders=include_key_placeholders))


@mcp_app.command("add")
def mcp_add(
    target: str = typer.Argument(..., help="Target CLI to add config to: 'claude' or 'codex'"),
) -> None:
    """Add MCP host configuration (Codex or Claude Code).

    Notes:
      This command writes no output to stdout.

    Examples:
      gsd mcp add codex
      gsd mcp add claude
    """
    stdout = sys.stdout
    try:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
        legacy_mcp_config_add(target=target)
    finally:
        try:
            sys.stdout.close()
        except Exception:  # noqa: BLE001
            pass
        sys.stdout = stdout


@mcp_app.command("smoke")
def mcp_smoke(
    url: str | None = typer.Option(None, "--url", help="Target URL for the web_eval_agent tool"),
    task: str | None = typer.Option(None, "--task", help="Task description for the evaluation"),
    host: str = typer.Option("127.0.0.1", "--host", help="Dashboard host (default 127.0.0.1)"),
    port: int = typer.Option(5009, "--port", help="Dashboard port (default 5009)"),
    timeout: float = typer.Option(20.0, "--timeout", help="Seconds to wait for dashboard startup"),
    headless: bool = typer.Option(True, "--headless", is_flag=True, help="Run Playwright headless"),
    no_headless: bool = typer.Option(
        False, "--no-headless", is_flag=True, help="Run Playwright with a visible browser"
    ),
    skip_browser_task: bool = typer.Option(
        False, "--skip-browser-task", help="Skip Playwright navigation (infra-only checks)"
    ),
    expect_streaming_mode: str = typer.Option(
        "cdp", "--expect-streaming-mode", help="Assert /healthz reports this mode"
    ),
    output: str | None = typer.Option(None, "--output", help="Optional path to write JSON report"),
    verbose: bool = typer.Option(False, "--verbose", help="Print verbose JSON report"),
) -> None:
    """Run MCP smoke checks (dashboard + tool contract).

    Examples:
      gsd mcp smoke
      gsd mcp smoke --no-headless --verbose
    """
    legacy_mcp_tool_smoke(
        url=url,
        task=task,
        host=host,
        port=port,
        timeout=timeout,
        headless=headless,
        no_headless=no_headless,
        skip_browser_task=skip_browser_task,
        expect_streaming_mode=expect_streaming_mode,
        output=output,
        verbose=verbose,
    )


tools_app = typer.Typer(help="MCP tool exposure controls", add_completion=False)
mcp_app.add_typer(tools_app, name="tools")


@config_app.callback()
def _config_callback() -> None:
    """Manage the stable per-user `.env` config.

    Examples:
      gsd config --help
      gsd config init
    """


@browser_app.callback()
def _browser_callback() -> None:
    """Browser install/state utilities.

    Examples:
      gsd browser --help
      gsd browser ensure
    """


@stream_app.callback()
def _stream_callback() -> None:
    """Streaming server + dashboard commands.

    Examples:
      gsd stream --help
      gsd stream serve
    """


@llm_app.callback()
def _llm_callback() -> None:
    """LLM/provider validation helpers.

    Examples:
      gsd llm --help
      gsd llm validate
    """


@dev_app.callback()
def _dev_callback() -> None:
    """Developer/debug-only commands.

    Examples:
      gsd dev --help
      gsd dev diagnose
    """


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
    """Start the FastMCP stdio server (stdout is reserved for JSON-RPC).

    Examples:
      gsd mcp serve
      gsd mcp serve --log-level DEBUG
    """

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
