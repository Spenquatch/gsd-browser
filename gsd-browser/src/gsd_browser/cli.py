"""Typer CLI entry point for the GSD Browser MCP server."""

from __future__ import annotations

import typer
from rich.console import Console

from . import __version__
from .config import load_settings
from .logging_utils import setup_logging
from .main import serve_stdio

console = Console()
app = typer.Typer(help="GSD Browser MCP server CLI")


@app.callback()
def callback(
    version: bool = typer.Option(False, "--version", help="Print version and exit"),
) -> None:
    """Base callback for global options."""
    if version:
        console.print(f"gsd-browser v{__version__}")
        raise typer.Exit()


@app.command()
def serve(
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
    """Start the FastMCP stdio server."""
    overrides: dict[str, str] = {}
    if llm_provider is not None:
        overrides["GSD_BROWSER_LLM_PROVIDER"] = llm_provider
    if llm_model is not None:
        overrides["GSD_BROWSER_MODEL"] = llm_model
    if ollama_host is not None:
        overrides["OLLAMA_HOST"] = ollama_host

    settings = load_settings(env=overrides or None)

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
        "[green]Config loaded[/green]: "
        f"llm_provider={settings.llm_provider}, model={settings.model}, "
        f"log_level={desired_level}, json_logs={desired_json}"
    )
    from .mcp_server import run_stdio

    run_stdio()


@app.command("serve-echo")
def serve_echo(
    disable_echo: bool = typer.Option(
        False, "--no-echo", is_flag=True, help="Disable echoing stdin back to stdout"
    ),
    once: bool = typer.Option(
        False, "--once", is_flag=True, help="Process a single message then exit"
    ),
) -> None:
    """Start a tiny echo loop (debugging only)."""
    setup_logging("INFO", json_logs=False)
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
    llm_provider: str | None = typer.Option(
        None,
        "--llm-provider",
        help="LLM provider (anthropic, chatbrowseruse, openai, ollama)",
    ),
    llm_model: str | None = typer.Option(None, "--llm-model", help="Override LLM model name"),
    ollama_host: str | None = typer.Option(None, "--ollama-host", help="Override OLLAMA_HOST"),
) -> None:
    """Start the browser streaming server (Socket.IO + /healthz)."""
    overrides: dict[str, str] = {}
    if llm_provider is not None:
        overrides["GSD_BROWSER_LLM_PROVIDER"] = llm_provider
    if llm_model is not None:
        overrides["GSD_BROWSER_MODEL"] = llm_model
    if ollama_host is not None:
        overrides["OLLAMA_HOST"] = ollama_host

    settings = load_settings(env=overrides or None, strict=False)

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
    """Run lightweight environment diagnostics."""
    import os
    import platform
    import shutil

    settings = load_settings(strict=False)

    console.print(f"[bold]System[/bold]: {platform.platform()}")
    console.print(f"[bold]Python[/bold]: {platform.python_version()}")
    for tool in ("uv", "poetry", "pipx", "gsd-browser"):
        path = shutil.which(tool)
        console.print(f"[bold]{tool}[/bold]: {path or '(not found)'}")

    console.print("[bold]Environment[/bold]:")
    for key in (
        "GSD_BROWSER_LLM_PROVIDER",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "BROWSER_USE_API_KEY",
        "OLLAMA_HOST",
        "GSD_BROWSER_MODEL",
        "LOG_LEVEL",
        "GSD_BROWSER_JSON_LOGS",
    ):
        present = "set" if os.environ.get(key) else "unset"
        console.print(f"- {key}: {present}")

    console.print(
        f"[bold]Config[/bold]: llm_provider={settings.llm_provider}, model={settings.model}, "
        f"streaming={settings.streaming_mode}/{settings.streaming_quality}"
    )
    console.print("[bold]MCP snippet[/bold]:")
    console.print(settings.to_mcp_snippet())


@app.command("validate-llm")
def validate_llm(
    llm_provider: str | None = typer.Option(
        None,
        "--llm-provider",
        help="LLM provider (anthropic, chatbrowseruse, openai, ollama)",
    ),
    llm_model: str | None = typer.Option(None, "--llm-model", help="Override LLM model name"),
    ollama_host: str | None = typer.Option(None, "--ollama-host", help="Override OLLAMA_HOST"),
) -> None:
    """Validate LLM provider configuration for browser-use."""
    overrides: dict[str, str] = {}
    if llm_provider is not None:
        overrides["GSD_BROWSER_LLM_PROVIDER"] = llm_provider
    if llm_model is not None:
        overrides["GSD_BROWSER_MODEL"] = llm_model
    if ollama_host is not None:
        overrides["OLLAMA_HOST"] = ollama_host

    settings = load_settings(env=overrides or None, strict=False)
    from .llm.browser_use import validate_llm_settings

    try:
        validate_llm_settings(settings)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(
        "[green]LLM config valid[/green]: "
        f"llm_provider={settings.llm_provider}, model={settings.model}"
    )


@app.command()
def smoke() -> None:
    """Run a minimal runtime smoke (dashboard + screenshot storage)."""
    import json
    import urllib.request

    from .runtime import DEFAULT_DASHBOARD_HOST, DEFAULT_DASHBOARD_PORT, get_runtime

    settings = load_settings(strict=False)
    runtime = get_runtime()
    dashboard = runtime.ensure_dashboard_running(
        settings=settings, host=DEFAULT_DASHBOARD_HOST, port=DEFAULT_DASHBOARD_PORT
    )
    url = f"http://{dashboard.host}:{dashboard.port}/healthz"
    with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
        payload = json.loads(resp.read().decode("utf-8"))
    console.print("[green]Dashboard healthy[/green]")
    console.print(payload)


@app.command("mcp-tool-smoke")
def mcp_tool_smoke(
    url: str | None = typer.Option(None, "--url", help="Target URL for the web_eval_agent tool"),
    task: str | None = typer.Option(None, "--task", help="Task description for the evaluation"),
    host: str = typer.Option("127.0.0.1", "--host", help="Dashboard host (default 127.0.0.1)"),
    port: int = typer.Option(5009, "--port", help="Dashboard port (default 5009)"),
    timeout: float = typer.Option(20.0, "--timeout", help="Seconds to wait for dashboard startup"),
    headless: bool = typer.Option(
        True, "--headless/--no-headless", help="Run Playwright in headless mode"
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
    """Run the MCP tool + dashboard smoke check."""
    from . import mcp_tool_smoke as smoke_mod

    argv: list[str] = []
    argv += ["--url", url or smoke_mod.DEFAULT_URL]
    argv += ["--task", task or smoke_mod.DEFAULT_TASK]
    argv += ["--host", host]
    argv += ["--port", str(port)]
    argv += ["--timeout", str(timeout)]
    argv += ["--headless" if headless else "--no-headless"]
    if skip_browser_task:
        argv += ["--skip-browser-task"]
    argv += ["--expect-streaming-mode", expect_streaming_mode]
    if output:
        argv += ["--output", output]
    if verbose:
        argv += ["--verbose"]

    smoke_mod.main(argv)


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
