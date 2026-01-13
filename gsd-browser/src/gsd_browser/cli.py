"""Typer CLI entry point for the GSD Browser MCP server."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console

from . import __version__
from .browser_install import (
    detect_local_browser_executable,
    install_playwright_chromium,
    should_use_with_deps,
)
from .config import load_settings
from .logging_utils import setup_logging
from .main import serve_stdio
from .mcp_tool_policy import (
    KNOWN_MCP_TOOLS,
    compute_tool_exposure_policy,
    normalize_tool_name,
    parse_tool_selector,
)
from .user_config import default_env_path, ensure_env_file, update_env_file

console = Console()
app = typer.Typer(help="GSD Browser MCP server CLI", invoke_without_command=True)
mcp_tools_app = typer.Typer(help="Manage MCP tool exposure (enable/disable tools)")
app.add_typer(mcp_tools_app, name="mcp-tools")

_MCP_TOOLS_ENABLE_ARG = typer.Argument(..., help="Tool name(s) to enable")
_MCP_TOOLS_DISABLE_ARG = typer.Argument(..., help="Tool name(s) to disable")
_MCP_TOOLS_SET_ENABLED_ARG = typer.Argument(None, help="Tool name(s) to allowlist")
_MCP_TOOLS_SET_DISABLED_ARG = typer.Argument(None, help="Tool name(s) to denylist")


def _env_path_for_user_config() -> Path:
    override = (os.getenv("GSD_BROWSER_ENV_FILE") or "").strip()
    return Path(override).expanduser() if override else default_env_path()


def _read_env_file_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _format_tools(tools: set[str]) -> str:
    return ",".join(sorted(tools))


def _validate_tool_names(tools: list[str]) -> list[str]:
    normalized = [normalize_tool_name(t) for t in tools]
    known = set(KNOWN_MCP_TOOLS)
    unknown = sorted({t for t in normalized if t not in known})
    if unknown:
        console.print(f"[red]Unknown tool(s)[/red]: {', '.join(unknown)}")
        console.print(f"[dim]Known tools[/dim]: {', '.join(KNOWN_MCP_TOOLS)}")
        raise typer.Exit(code=2)
    return normalized


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
        typer.echo("Cannot use --json-logs and --text-logs together", err=True)
        raise typer.Exit(code=1)
    if json_logs:
        desired_json = True
    elif text_logs:
        desired_json = False
    else:
        desired_json = settings.json_logs

    setup_logging(desired_level, json_logs=desired_json)
    # IMPORTANT: MCP stdio transport uses stdout for JSON-RPC. Do not print to stdout here.
    typer.echo(
        "Starting MCP stdio server: "
        f"llm_provider={settings.llm_provider}, model={settings.model}, "
        f"log_level={desired_level}, json_logs={desired_json}",
        err=True,
    )
    from .mcp_server import apply_configured_tool_policy, run_stdio

    apply_configured_tool_policy(settings=settings)
    run_stdio()


@app.command("list-tools")
def list_tools() -> None:
    """Print known MCP tool names and the currently advertised set (after policy)."""

    env_path = _env_path_for_user_config()
    ensure_env_file(path=env_path, overwrite=False)
    file_values = _read_env_file_values(env_path)

    settings = load_settings(strict=False)
    policy = compute_tool_exposure_policy(
        known_tools=set(KNOWN_MCP_TOOLS),
        enabled_raw=settings.mcp_enabled_tools,
        disabled_raw=settings.mcp_disabled_tools,
    )

    console.print(f"[dim]Config[/dim]: {env_path}")
    file_enabled = file_values.get("GSD_BROWSER_MCP_ENABLED_TOOLS", "")
    file_disabled = file_values.get("GSD_BROWSER_MCP_DISABLED_TOOLS", "")
    console.print(f"[dim].env enabled[/dim]: {file_enabled}")
    console.print(f"[dim].env disabled[/dim]: {file_disabled}")
    console.print(f"[dim]Effective enabled[/dim]: {settings.mcp_enabled_tools}")
    console.print(f"[dim]Effective disabled[/dim]: {settings.mcp_disabled_tools}")

    console.print(f"[green]Advertised tools[/green]: {_format_tools(policy.advertised_tools)}")
    if policy.unknown_requested:
        console.print(
            f"[yellow]Unknown requested[/yellow]: {_format_tools(policy.unknown_requested)}"
        )

    for name in KNOWN_MCP_TOOLS:
        status = "ENABLED" if name in policy.advertised_tools else "disabled"
        color = "green" if status == "ENABLED" else "dim"
        console.print(f"[{color}]{name}[/{color}] {status}")


@mcp_tools_app.command("list")
def mcp_tools_list() -> None:
    """Alias for `gsd-browser list-tools`."""

    list_tools()


@mcp_tools_app.command("enable")
def mcp_tools_enable(
    tools: list[str] = _MCP_TOOLS_ENABLE_ARG,
) -> None:
    """Enable one or more MCP tools in the user config (.env)."""

    normalized = _validate_tool_names(tools)
    env_path = _env_path_for_user_config()
    ensure_env_file(path=env_path, overwrite=False)
    current = _read_env_file_values(env_path)

    known = set(KNOWN_MCP_TOOLS)
    enabled_raw = current.get("GSD_BROWSER_MCP_ENABLED_TOOLS", "")
    disabled_raw = current.get("GSD_BROWSER_MCP_DISABLED_TOOLS", "")

    enabled_mode, enabled_names = parse_tool_selector(enabled_raw)
    _disabled_mode, disabled_names = parse_tool_selector(disabled_raw)

    next_disabled = (disabled_names - set(normalized)) & known

    if enabled_mode == "none":
        next_enabled = set(normalized)
        next_enabled_raw = _format_tools(next_enabled)
    elif enabled_mode == "all":
        next_enabled_raw = enabled_raw.strip() or "all"
    elif enabled_raw.strip():
        next_enabled = (enabled_names | set(normalized)) & known
        next_enabled_raw = _format_tools(next_enabled)
    else:
        next_enabled_raw = ""

    updates = {
        "GSD_BROWSER_MCP_ENABLED_TOOLS": next_enabled_raw,
        "GSD_BROWSER_MCP_DISABLED_TOOLS": _format_tools(next_disabled),
    }
    update_env_file(path=env_path, updates=updates)
    console.print(f"[green]✓ Enabled[/green]: {', '.join(normalized)}")
    console.print(f"[dim]Updated[/dim]: {env_path}")


@mcp_tools_app.command("disable")
def mcp_tools_disable(
    tools: list[str] = _MCP_TOOLS_DISABLE_ARG,
) -> None:
    """Disable one or more MCP tools in the user config (.env)."""

    normalized = _validate_tool_names(tools)
    env_path = _env_path_for_user_config()
    ensure_env_file(path=env_path, overwrite=False)
    current = _read_env_file_values(env_path)

    known = set(KNOWN_MCP_TOOLS)
    enabled_raw = current.get("GSD_BROWSER_MCP_ENABLED_TOOLS", "")
    disabled_raw = current.get("GSD_BROWSER_MCP_DISABLED_TOOLS", "")

    enabled_mode, enabled_names = parse_tool_selector(enabled_raw)
    _disabled_mode, disabled_names = parse_tool_selector(disabled_raw)

    next_disabled = (disabled_names | set(normalized)) & known

    updates: dict[str, str] = {"GSD_BROWSER_MCP_DISABLED_TOOLS": _format_tools(next_disabled)}
    if enabled_mode == "all" or not enabled_raw.strip():
        # Baseline is all tools; leave allowlist untouched.
        pass
    elif enabled_mode == "none":
        updates["GSD_BROWSER_MCP_ENABLED_TOOLS"] = "none"
    else:
        next_enabled = (enabled_names - set(normalized)) & known
        updates["GSD_BROWSER_MCP_ENABLED_TOOLS"] = _format_tools(next_enabled)

    update_env_file(path=env_path, updates=updates)
    console.print(f"[green]✓ Disabled[/green]: {', '.join(normalized)}")
    console.print(f"[dim]Updated[/dim]: {env_path}")


@mcp_tools_app.command("reset")
def mcp_tools_reset() -> None:
    """Clear allow/deny lists (defaults to all tools enabled)."""

    env_path = _env_path_for_user_config()
    ensure_env_file(path=env_path, overwrite=False)
    update_env_file(
        path=env_path,
        updates={"GSD_BROWSER_MCP_ENABLED_TOOLS": "", "GSD_BROWSER_MCP_DISABLED_TOOLS": ""},
    )
    console.print("[green]✓ Reset MCP tool policy[/green]")
    console.print(f"[dim]Updated[/dim]: {env_path}")


@mcp_tools_app.command("set-enabled")
def mcp_tools_set_enabled(
    tools: list[str] | None = _MCP_TOOLS_SET_ENABLED_ARG,
    all_tools: bool = typer.Option(False, "--all", help="Allowlist all tools (baseline=all)"),
    none: bool = typer.Option(False, "--none", help="Allowlist no tools (baseline=none)"),
    clear: bool = typer.Option(False, "--clear", help="Unset allowlist (defaults to all tools)"),
) -> None:
    """Set the MCP allowlist (GSD_BROWSER_MCP_ENABLED_TOOLS)."""

    if sum([bool(all_tools), bool(none), bool(clear)]) > 1:
        console.print("[red]Use only one of --all, --none, or --clear[/red]")
        raise typer.Exit(code=2)

    env_path = _env_path_for_user_config()
    ensure_env_file(path=env_path, overwrite=False)

    if clear:
        update_env_file(path=env_path, updates={"GSD_BROWSER_MCP_ENABLED_TOOLS": ""})
        console.print("[green]✓ Cleared allowlist[/green]")
        console.print(f"[dim]Updated[/dim]: {env_path}")
        return

    if all_tools:
        update_env_file(path=env_path, updates={"GSD_BROWSER_MCP_ENABLED_TOOLS": "all"})
        console.print("[green]✓ Set allowlist[/green]: all")
        console.print(f"[dim]Updated[/dim]: {env_path}")
        return

    if none:
        update_env_file(path=env_path, updates={"GSD_BROWSER_MCP_ENABLED_TOOLS": "none"})
        console.print("[green]✓ Set allowlist[/green]: none")
        console.print(f"[dim]Updated[/dim]: {env_path}")
        return

    tools = tools or []
    if not tools:
        console.print("[red]Provide tool names or use --all/--none/--clear[/red]")
        raise typer.Exit(code=2)

    normalized = _validate_tool_names(tools)
    update_env_file(
        path=env_path, updates={"GSD_BROWSER_MCP_ENABLED_TOOLS": _format_tools(set(normalized))}
    )
    console.print(f"[green]✓ Set allowlist[/green]: {', '.join(normalized)}")
    console.print(f"[dim]Updated[/dim]: {env_path}")


@mcp_tools_app.command("set-disabled")
def mcp_tools_set_disabled(
    tools: list[str] | None = _MCP_TOOLS_SET_DISABLED_ARG,
    clear: bool = typer.Option(False, "--clear", help="Clear denylist"),
) -> None:
    """Set the MCP denylist (GSD_BROWSER_MCP_DISABLED_TOOLS)."""

    env_path = _env_path_for_user_config()
    ensure_env_file(path=env_path, overwrite=False)

    if clear:
        update_env_file(path=env_path, updates={"GSD_BROWSER_MCP_DISABLED_TOOLS": ""})
        console.print("[green]✓ Cleared denylist[/green]")
        console.print(f"[dim]Updated[/dim]: {env_path}")
        return

    tools = tools or []
    if not tools:
        console.print("[red]Provide tool names or use --clear[/red]")
        raise typer.Exit(code=2)

    normalized = _validate_tool_names(tools)
    update_env_file(
        path=env_path, updates={"GSD_BROWSER_MCP_DISABLED_TOOLS": _format_tools(set(normalized))}
    )
    console.print(f"[green]✓ Set denylist[/green]: {', '.join(normalized)}")
    console.print(f"[dim]Updated[/dim]: {env_path}")


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
    """Run the MCP tool + dashboard smoke check."""
    from . import mcp_tool_smoke as smoke_mod

    if no_headless:
        headless = False

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
    include_key_placeholders: bool = typer.Option(
        False,
        "--include-key-placeholders",
        help="Emit ${VAR} placeholders for API keys (some MCP hosts expand these; Codex does not).",
    ),
) -> None:
    """Print MCP configuration snippet for the CLI."""
    settings = load_settings(strict=False)
    fmt_normalized = format.lower()
    if fmt_normalized == "toml":
        typer.echo(settings.to_mcp_toml(include_key_placeholders=include_key_placeholders))
    else:
        typer.echo(settings.to_mcp_snippet(include_key_placeholders=include_key_placeholders))


@app.command("init-env")
def init_env(
    path: Path | None = typer.Option(  # noqa: B008
        None,
        "--path",
        help=(
            "Optional destination path for the user .env file "
            "(default: ~/.config/gsd-browser/.env)"
        ),
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        is_flag=True,
        help="Overwrite the env file if it already exists",
    ),
) -> None:
    """Create a user-level env file for production installs."""
    env_path = ensure_env_file(path=path, overwrite=overwrite)
    console.print(f"[green]✓ Wrote env file[/green]: {env_path}")
    console.print("[dim]Edit this file to add API keys (ANTHROPIC_API_KEY / OPENAI_API_KEY).[/dim]")


@app.command("configure")
def configure(
    env_path: Path | None = typer.Option(  # noqa: B008
        None,
        "--env-path",
        help="Path to the user env file (default: ~/.config/gsd-browser/.env)",
    ),
    anthropic_api_key: str | None = typer.Option(
        None,
        "--anthropic-api-key",
        help="Write ANTHROPIC_API_KEY to the env file (use with care; stored on disk).",
    ),
    openai_api_key: str | None = typer.Option(
        None,
        "--openai-api-key",
        help="Write OPENAI_API_KEY to the env file (use with care; stored on disk).",
    ),
    browser_use_api_key: str | None = typer.Option(
        None,
        "--browser-use-api-key",
        help="Write BROWSER_USE_API_KEY to the env file (use with care; stored on disk).",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        is_flag=True,
        help="Do not prompt; only apply provided flags",
    ),
) -> None:
    """Initialize and/or update user config at a stable location."""
    path = env_path or default_env_path()
    ensure_env_file(path=path, overwrite=False)

    updates: dict[str, str] = {}
    if anthropic_api_key is not None:
        updates["ANTHROPIC_API_KEY"] = anthropic_api_key
    if openai_api_key is not None:
        updates["OPENAI_API_KEY"] = openai_api_key
    if browser_use_api_key is not None:
        updates["BROWSER_USE_API_KEY"] = browser_use_api_key

    if not updates and not non_interactive:
        if sys.stdin.isatty():
            if typer.confirm("Set ANTHROPIC_API_KEY now?", default=False):
                updates["ANTHROPIC_API_KEY"] = typer.prompt(
                    "ANTHROPIC_API_KEY", hide_input=True, confirmation_prompt=True
                )
            if typer.confirm("Set OPENAI_API_KEY now?", default=False):
                updates["OPENAI_API_KEY"] = typer.prompt(
                    "OPENAI_API_KEY", hide_input=True, confirmation_prompt=True
                )
            if typer.confirm("Set BROWSER_USE_API_KEY now?", default=False):
                updates["BROWSER_USE_API_KEY"] = typer.prompt(
                    "BROWSER_USE_API_KEY", hide_input=True, confirmation_prompt=True
                )

    if updates:
        update_env_file(path=path, updates=updates)
        console.print(f"[green]✓ Updated[/green]: {path}")
    else:
        console.print(f"[green]✓ Ready[/green]: {path}")


@app.command("ensure-browser")
def ensure_browser(
    install: bool = typer.Option(
        True,
        "--install/--no-install",
        help="Install Playwright Chromium if no local browser is detected",
    ),
    write_config: bool = typer.Option(
        False,
        "--write-config/--no-write-config",
        help="Persist detected browser path to the user .env file.",
    ),
    with_deps: bool | None = typer.Option(
        None,
        "--with-deps/--no-with-deps",
        help="Use `playwright install --with-deps` on Linux (root-only).",
    ),
) -> None:
    """Ensure a local Chromium/Chrome executable exists for browser-use."""
    found = detect_local_browser_executable()
    if found:
        console.print(f"[green]✓ Browser found[/green]: {found}")
        if write_config:
            env_file = (os.getenv("GSD_BROWSER_ENV_FILE") or "").strip()
            env_path = Path(env_file).expanduser() if env_file else default_env_path()
            ensure_env_file(path=env_path, overwrite=False)
            update_env_file(
                path=env_path, updates={"GSD_BROWSER_BROWSER_EXECUTABLE_PATH": str(found)}
            )
            console.print(f"[dim]Pinned in config[/dim]: {env_path}")
        return

    console.print("[yellow]! No local browser executable detected[/yellow]")
    if not install:
        raise typer.Exit(code=1)

    deps = should_use_with_deps() if with_deps is None else bool(with_deps)
    if deps and should_use_with_deps() is False and with_deps is True:
        console.print(
            "[yellow]! --with-deps requested but not available; continuing without it[/yellow]"
        )
        deps = False

    console.print("[dim]Installing Playwright Chromium...[/dim]")
    result = install_playwright_chromium(with_deps=deps)
    if result.returncode != 0:
        console.print("[red]✗ Failed to install Chromium via Playwright[/red]")
        if result.stderr:
            console.print(result.stderr.strip())
        raise typer.Exit(code=result.returncode)

    found_after = detect_local_browser_executable()
    if not found_after:
        pw_path = (os.getenv("PLAYWRIGHT_BROWSERS_PATH") or "").strip()
        console.print(
            "[red]✗ Playwright install finished, but no browser executable was detected[/red]"
        )
        if pw_path:
            console.print(f"[yellow]PLAYWRIGHT_BROWSERS_PATH[/yellow]: {pw_path}")
        if result.stdout.strip():
            console.print("[dim]playwright stdout:[/dim]")
            console.print(result.stdout.strip())
        if result.stderr.strip():
            console.print("[dim]playwright stderr:[/dim]")
            console.print(result.stderr.strip())
        raise typer.Exit(code=2)

    console.print(f"[green]✓ Browser installed[/green]: {found_after}")
    if write_config:
        env_file = (os.getenv("GSD_BROWSER_ENV_FILE") or "").strip()
        env_path = Path(env_file).expanduser() if env_file else default_env_path()
        ensure_env_file(path=env_path, overwrite=False)
        update_env_file(path=env_path, updates={"GSD_BROWSER_BROWSER_EXECUTABLE_PATH": found_after})
        console.print(f"[dim]Pinned in config[/dim]: {env_path}")


@app.command("mcp-config-add")
def mcp_config_add(
    target: str = typer.Argument(
        ...,
        help="Target CLI to add config to: 'claude' or 'codex'",
    ),
) -> None:
    """Add gsd-browser MCP server config to Claude Code or Codex."""
    target_normalized = target.lower()

    if target_normalized not in ["claude", "codex"]:
        console.print(f"[red]Error: Unknown target '{target}'. Use 'claude' or 'codex'.[/red]")
        raise typer.Exit(1)

    env_path = ensure_env_file(overwrite=False)
    console.print(f"[dim]Using user env file: {env_path}[/dim]")

    settings = load_settings(strict=False)

    # Try using native CLI commands first
    if target_normalized == "claude":
        success = _add_to_claude_via_cli(settings)
        if not success:
            console.print(
                "[yellow]Native 'claude mcp add' command not found, "
                "trying direct file modification...[/yellow]"
            )
            _add_to_claude_direct(settings)
    else:  # codex
        success = _add_to_codex_via_cli(settings)
        if not success:
            console.print(
                "[yellow]Native 'codex mcp add' command not found, "
                "trying direct file modification...[/yellow]"
            )
            _add_to_codex_direct(settings)


def _add_to_claude_via_cli(settings) -> bool:
    """Try to add MCP config using 'claude mcp add' command."""
    try:
        # Check if claude command exists
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False

        # Try to add the MCP server
        mcp_json = settings.to_mcp_snippet()
        config_data = json.loads(mcp_json)
        server_config = config_data["mcpServers"]["gsd-browser"]

        # Build command: claude mcp add --transport stdio -e KEY=value -- name command args
        # IMPORTANT: The -- separator comes BEFORE the server name, command, and args
        cmd = ["claude", "mcp", "add", "--transport", "stdio"]

        # Add environment variables with -e flag
        for key, value in server_config["env"].items():
            cmd.extend(["-e", f"{key}={value}"])

        # Add -- separator (comes BEFORE server name)
        cmd.append("--")

        # Add server name, then command and args
        cmd.append("gsd-browser")
        cmd.append(server_config["command"])
        cmd.extend(server_config["args"])

        # Debug: print the command being run
        typer.echo(f"Running command: {' '.join(cmd)}", err=True)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            console.print("[green]✓ Successfully added gsd-browser to Claude Code config![/green]")
            return True
        else:
            console.print(f"[yellow]'claude mcp add' failed: {result.stderr.strip()}[/yellow]")
            return False

    except subprocess.TimeoutExpired:
        console.print("[yellow]Timeout running 'claude mcp add' command[/yellow]")
        return False
    except FileNotFoundError:
        console.print("[yellow]'claude' command not found in PATH[/yellow]")
        return False
    except Exception as e:
        console.print(f"[yellow]Unexpected error running 'claude mcp add': {e}[/yellow]")
        return False


def _add_to_codex_via_cli(settings) -> bool:
    """Try to add MCP config using 'codex mcp add' command."""
    try:
        # Check if codex command exists
        result = subprocess.run(
            ["codex", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False

        # Ensure the user env file exists so the server can boot even if the shell env is empty.
        ensure_env_file(overwrite=False)

        # Build command: codex mcp add gsd-browser --env KEY=VALUE -- gsd-browser serve
        env = settings._mcp_env()
        cmd = ["codex", "mcp", "add", "gsd-browser"]
        for key, value in env.items():
            cmd.extend(["--env", f"{key}={value}"])
        cmd.append("--")
        cmd.extend(["gsd-browser", "serve"])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

        if result.returncode == 0:
            console.print("[green]✓ Successfully added gsd-browser to Codex config![/green]")
            return True
        else:
            console.print(f"[yellow]Codex command failed: {result.stderr}[/yellow]")
            return False

    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False


def _add_to_claude_direct(settings) -> None:
    """Directly modify Claude Code config file."""
    # Common Claude Code config locations
    possible_paths = [
        Path.home() / ".claude" / "config.json",
        Path.home() / ".config" / "claude" / "config.json",
        Path.home() / ".claude.json",
    ]

    config_path = None
    for path in possible_paths:
        if path.exists():
            config_path = path
            break

    if not config_path:
        # Create default location
        config_path = Path.home() / ".claude" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

    # Load or create config
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
    else:
        config = {}

    # Ensure mcpServers exists
    if "mcpServers" not in config:
        config["mcpServers"] = {}

    # Add gsd-browser config
    mcp_json = settings.to_mcp_snippet()
    config_data = json.loads(mcp_json)
    config["mcpServers"]["gsd-browser"] = config_data["mcpServers"]["gsd-browser"]

    # Write back
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    console.print(f"[green]✓ Successfully added gsd-browser to {config_path}![/green]")


def _add_to_codex_direct(settings) -> None:
    """Directly modify Codex config file."""
    config_path = Path.home() / ".codex" / "config.toml"

    if not config_path.parent.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)

    mcp_toml = settings.to_mcp_toml()

    # Check if file exists and has gsd-browser already
    if config_path.exists():
        content = config_path.read_text()
        if "[mcp_servers.gsd-browser]" in content:
            console.print(
                "[yellow]! gsd-browser already exists in Codex config, skipping.[/yellow]"
            )
            console.print(f"[yellow]  Edit manually at: {config_path}[/yellow]")
            return

        # Append to existing file
        with open(config_path, "a") as f:
            f.write("\n\n# GSD Browser MCP Server\n")
            f.write(mcp_toml)
    else:
        # Create new file
        with open(config_path, "w") as f:
            f.write("# Codex MCP Configuration\n\n")
            f.write("# GSD Browser MCP Server\n")
            f.write(mcp_toml)

    console.print(f"[green]✓ Successfully added gsd-browser to {config_path}![/green]")


if __name__ == "__main__":
    app()
