"""Canonical `gsd` CLI entry point.

This file intentionally starts small and grows as tasks in `tasks.json` are completed.
"""

from __future__ import annotations

import os
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
from .cli import diagnose as legacy_diagnose
from .cli import mcp_config_add as legacy_mcp_config_add
from .cli import mcp_tool_smoke as legacy_mcp_tool_smoke
from .cli import serve as legacy_serve
from .cli import serve_browser as legacy_serve_browser
from .cli import serve_echo as legacy_serve_echo
from .cli import smoke as legacy_smoke
from .cli import validate_llm as legacy_validate_llm
from .config import load_settings
from .mcp_tool_policy import (
    KNOWN_MCP_TOOLS,
    compute_tool_exposure_policy,
    normalize_tool_name,
    parse_tool_selector,
)
from .user_config import default_env_path, ensure_env_file, update_env_file

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


tools_app = typer.Typer(
    help="MCP tool exposure controls",
    add_completion=False,
    epilog="Examples:\n  gsd mcp tools list\n  gsd mcp tools disable setup_browser_state\n",
)
mcp_app.add_typer(tools_app, name="tools")

_TOOLS_ENABLE_ARG = typer.Argument(..., help="Tool name(s) to enable")
_TOOLS_DISABLE_ARG = typer.Argument(..., help="Tool name(s) to disable")
_TOOLS_ALLOW_ARG = typer.Argument(None, help="Tool name(s) to allowlist")
_TOOLS_DENY_ARG = typer.Argument(None, help="Tool name(s) to denylist")


def _tools_env_path() -> Path:
    override = (os.getenv("GSD_BROWSER_ENV_FILE") or "").strip()
    return default_env_path() if not override else Path(os.path.expanduser(override))


def _read_env_file_values(path: Path) -> dict[str, str]:
    try:
        raw = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    out: dict[str, str] = {}
    for line in raw:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _parse_tool_args(args: list[str]) -> list[str]:
    tokens: list[str] = []
    for raw in args:
        for piece in raw.split(","):
            name = piece.strip()
            if not name:
                continue
            tokens.append(name)

    normalized = [normalize_tool_name(name) for name in tokens]
    known = set(KNOWN_MCP_TOOLS)
    unknown = sorted({name for name in normalized if name not in known})
    if unknown:
        typer.echo(f"Unknown tool(s): {', '.join(unknown)}", err=True)
        typer.echo(f"Known tools: {', '.join(KNOWN_MCP_TOOLS)}", err=True)
        raise typer.Exit(code=2)

    # Dedupe while preserving deterministic order in storage (sorted later).
    return sorted(set(normalized))


def _format_tools_csv(tools: set[str]) -> str:
    return ",".join(sorted(tools))


def _emit_mutation_summary(env_path: Path) -> None:
    values = _read_env_file_values(env_path)
    enabled = values.get("GSD_BROWSER_MCP_ENABLED_TOOLS", "")
    disabled = values.get("GSD_BROWSER_MCP_DISABLED_TOOLS", "")

    typer.echo(f"Updated: {env_path}")
    typer.echo(f"GSD_BROWSER_MCP_ENABLED_TOOLS={enabled}")
    typer.echo(f"GSD_BROWSER_MCP_DISABLED_TOOLS={disabled}")
    typer.echo("Restart your MCP host/session")


@tools_app.command("list")
def tools_list() -> None:
    """List known tools and the effective advertised set.

    Examples:
      gsd mcp tools list
    """
    env_path = _tools_env_path()
    ensure_env_file(path=env_path, overwrite=False)

    settings = load_settings(strict=False)
    policy = compute_tool_exposure_policy(
        known_tools=set(KNOWN_MCP_TOOLS),
        enabled_raw=settings.mcp_enabled_tools,
        disabled_raw=settings.mcp_disabled_tools,
    )

    typer.echo(f"Config: {env_path}")
    typer.echo(f"Known tools: {_format_tools_csv(set(KNOWN_MCP_TOOLS))}")
    typer.echo(f"Advertised tools: {_format_tools_csv(policy.advertised_tools)}")


@tools_app.command("enable")
def tools_enable(tools: list[str] = _TOOLS_ENABLE_ARG) -> None:
    """Enable one or more MCP tools (removes from denylist; may set allowlist from none).

    Examples:
      gsd mcp tools enable setup_browser_state,get_screenshots
      gsd mcp tools enable setup_browser_state get_screenshots
    """
    env_path = _tools_env_path()
    ensure_env_file(path=env_path, overwrite=False)
    current = _read_env_file_values(env_path)

    requested = set(_parse_tool_args(tools))
    known = set(KNOWN_MCP_TOOLS)

    enabled_raw = current.get("GSD_BROWSER_MCP_ENABLED_TOOLS", "")
    disabled_raw = current.get("GSD_BROWSER_MCP_DISABLED_TOOLS", "")
    enabled_mode, enabled_names = parse_tool_selector(enabled_raw)
    _disabled_mode, disabled_names = parse_tool_selector(disabled_raw)

    next_disabled = (disabled_names - requested) & known

    updates: dict[str, str] = {"GSD_BROWSER_MCP_DISABLED_TOOLS": _format_tools_csv(next_disabled)}
    if enabled_mode == "none":
        updates["GSD_BROWSER_MCP_ENABLED_TOOLS"] = _format_tools_csv(requested)
    elif enabled_mode == "all" or not enabled_raw.strip():
        # Baseline is all tools; leave allowlist untouched.
        pass
    else:
        updates["GSD_BROWSER_MCP_ENABLED_TOOLS"] = _format_tools_csv(
            (enabled_names | requested) & known
        )

    update_env_file(path=env_path, updates=updates)
    _emit_mutation_summary(env_path)


@tools_app.command("disable")
def tools_disable(tools: list[str] = _TOOLS_DISABLE_ARG) -> None:
    """Disable one or more MCP tools (adds to denylist; removes from allowlist if present).

    Examples:
      gsd mcp tools disable setup_browser_state,get_screenshots
    """
    env_path = _tools_env_path()
    ensure_env_file(path=env_path, overwrite=False)
    current = _read_env_file_values(env_path)

    requested = set(_parse_tool_args(tools))
    known = set(KNOWN_MCP_TOOLS)

    enabled_raw = current.get("GSD_BROWSER_MCP_ENABLED_TOOLS", "")
    disabled_raw = current.get("GSD_BROWSER_MCP_DISABLED_TOOLS", "")
    enabled_mode, enabled_names = parse_tool_selector(enabled_raw)
    _disabled_mode, disabled_names = parse_tool_selector(disabled_raw)

    next_disabled = (disabled_names | requested) & known
    updates: dict[str, str] = {"GSD_BROWSER_MCP_DISABLED_TOOLS": _format_tools_csv(next_disabled)}

    if enabled_mode == "none":
        updates["GSD_BROWSER_MCP_ENABLED_TOOLS"] = "none"
    elif enabled_mode == "all" or not enabled_raw.strip():
        pass
    else:
        updates["GSD_BROWSER_MCP_ENABLED_TOOLS"] = _format_tools_csv(
            (enabled_names - requested) & known
        )

    update_env_file(path=env_path, updates=updates)
    _emit_mutation_summary(env_path)


@tools_app.command("allow")
def tools_allow(
    tools: list[str] = _TOOLS_ALLOW_ARG,
    all_tools: bool = typer.Option(False, "--all", help="Allowlist all tools (baseline=all)"),
    none: bool = typer.Option(False, "--none", help="Allowlist no tools (baseline=none)"),
    clear: bool = typer.Option(False, "--clear", help="Unset allowlist (defaults to all tools)"),
) -> None:
    """Set the allowlist (enabled tools selector).

    Examples:
      gsd mcp tools allow web_eval_agent,get_run_events
      gsd mcp tools allow --all
    """
    if sum([bool(all_tools), bool(none), bool(clear)]) > 1:
        raise typer.Exit(code=2)

    env_path = _tools_env_path()
    ensure_env_file(path=env_path, overwrite=False)

    if clear:
        update_env_file(path=env_path, updates={"GSD_BROWSER_MCP_ENABLED_TOOLS": ""})
        _emit_mutation_summary(env_path)
        return
    if all_tools:
        update_env_file(path=env_path, updates={"GSD_BROWSER_MCP_ENABLED_TOOLS": "all"})
        _emit_mutation_summary(env_path)
        return
    if none:
        update_env_file(path=env_path, updates={"GSD_BROWSER_MCP_ENABLED_TOOLS": "none"})
        _emit_mutation_summary(env_path)
        return

    tools = tools or []
    if not tools:
        raise typer.Exit(code=2)

    requested = set(_parse_tool_args(tools))
    update_env_file(
        path=env_path, updates={"GSD_BROWSER_MCP_ENABLED_TOOLS": _format_tools_csv(requested)}
    )
    _emit_mutation_summary(env_path)


@tools_app.command("deny")
def tools_deny(
    tools: list[str] = _TOOLS_DENY_ARG,
    clear: bool = typer.Option(False, "--clear", help="Clear denylist"),
) -> None:
    """Set the denylist (disabled tools selector).

    Examples:
      gsd mcp tools deny setup_browser_state,get_screenshots
      gsd mcp tools deny --clear
    """
    env_path = _tools_env_path()
    ensure_env_file(path=env_path, overwrite=False)

    if clear:
        update_env_file(path=env_path, updates={"GSD_BROWSER_MCP_DISABLED_TOOLS": ""})
        _emit_mutation_summary(env_path)
        return

    tools = tools or []
    if not tools:
        raise typer.Exit(code=2)

    requested = set(_parse_tool_args(tools))
    update_env_file(
        path=env_path, updates={"GSD_BROWSER_MCP_DISABLED_TOOLS": _format_tools_csv(requested)}
    )
    _emit_mutation_summary(env_path)


@tools_app.command("reset")
def tools_reset() -> None:
    """Reset allowlist and denylist (defaults to all tools enabled).

    Examples:
      gsd mcp tools reset
    """
    env_path = _tools_env_path()
    ensure_env_file(path=env_path, overwrite=False)
    update_env_file(
        path=env_path,
        updates={"GSD_BROWSER_MCP_ENABLED_TOOLS": "", "GSD_BROWSER_MCP_DISABLED_TOOLS": ""},
    )
    _emit_mutation_summary(env_path)


@config_app.callback()
def _config_callback() -> None:
    """Manage the stable per-user `.env` config.

    Examples:
      gsd config --help
      gsd config init
    """


def _select_env_path(*, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser()
    override = (os.getenv("GSD_BROWSER_ENV_FILE") or "").strip()
    if override:
        return Path(os.path.expanduser(override))
    return default_env_path()


@config_app.command("path")
def config_path() -> None:
    """Print the effective config path.

    Examples:
      gsd config path
    """
    typer.echo(str(_select_env_path(explicit=None)))


@config_app.command("init")
def config_init(
    path: Path | None = typer.Option(  # noqa: B008
        None,
        "--path",
        help="Optional destination path for the user .env file",
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite", is_flag=True, help="Overwrite the env file if it already exists"
    ),
) -> None:
    """Create the stable per-user `.env` file if missing.

    Examples:
      gsd config init
      gsd config init --overwrite
    """
    env_path = _select_env_path(explicit=path)
    wrote = overwrite or not env_path.exists()
    ensure_env_file(path=env_path, overwrite=overwrite)
    if wrote:
        typer.echo(f"Updated: {env_path}")


@config_app.command("set")
def config_set(
    env_path: Path | None = typer.Option(  # noqa: B008
        None,
        "--env-path",
        help="Path to the user env file",
    ),
    anthropic_api_key: str | None = typer.Option(
        None,
        "--anthropic-api-key",
        help="Write ANTHROPIC_API_KEY to the env file (stored on disk).",
    ),
    openai_api_key: str | None = typer.Option(
        None,
        "--openai-api-key",
        help="Write OPENAI_API_KEY to the env file (stored on disk).",
    ),
    browser_use_api_key: str | None = typer.Option(
        None,
        "--browser-use-api-key",
        help="Write BROWSER_USE_API_KEY to the env file (stored on disk).",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        is_flag=True,
        help="Do not prompt; only apply provided flags",
    ),
) -> None:
    """Update API keys in the stable `.env` file.

    Examples:
      gsd config set --anthropic-api-key sk-ant-...
      gsd config set --non-interactive --openai-api-key sk-...
    """
    target = _select_env_path(explicit=env_path)
    ensure_env_file(path=target, overwrite=False)

    updates: dict[str, str] = {}
    if anthropic_api_key is not None:
        updates["ANTHROPIC_API_KEY"] = anthropic_api_key
    if openai_api_key is not None:
        updates["OPENAI_API_KEY"] = openai_api_key
    if browser_use_api_key is not None:
        updates["BROWSER_USE_API_KEY"] = browser_use_api_key

    if not updates and not non_interactive and sys.stdin.isatty():
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

    if not updates:
        return

    update_env_file(path=target, updates=updates)
    typer.echo(f"Updated: {target}")


@browser_app.callback()
def _browser_callback() -> None:
    """Browser install/state utilities.

    Examples:
      gsd browser --help
      gsd browser ensure
    """


@browser_app.command("ensure")
def browser_ensure(
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
    """Ensure a local Chromium/Chrome executable exists for browser-use.

    Examples:
      gsd browser ensure
      gsd browser ensure --write-config
    """
    found = detect_local_browser_executable()
    if found:
        if write_config:
            env_path = _select_env_path(explicit=None)
            ensure_env_file(path=env_path, overwrite=False)
            update_env_file(
                path=env_path, updates={"GSD_BROWSER_BROWSER_EXECUTABLE_PATH": str(found)}
            )
            typer.echo(f"Updated: {env_path}")
        return

    if not install:
        raise typer.Exit(code=1)

    deps = should_use_with_deps() if with_deps is None else bool(with_deps)
    if deps and should_use_with_deps() is False and with_deps is True:
        deps = False

    result = install_playwright_chromium(with_deps=deps)
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)

    found_after = detect_local_browser_executable()
    if not found_after:
        raise typer.Exit(code=2)

    if write_config:
        env_path = _select_env_path(explicit=None)
        ensure_env_file(path=env_path, overwrite=False)
        update_env_file(path=env_path, updates={"GSD_BROWSER_BROWSER_EXECUTABLE_PATH": found_after})
        typer.echo(f"Updated: {env_path}")


@stream_app.callback()
def _stream_callback() -> None:
    """Streaming server + dashboard commands.

    Examples:
      gsd stream --help
      gsd stream serve
    """


@stream_app.command("serve")
def stream_serve(
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
        None, "--llm-provider", help="LLM provider (anthropic, chatbrowseruse, openai, ollama)"
    ),
    llm_model: str | None = typer.Option(None, "--llm-model", help="Override LLM model name"),
    ollama_host: str | None = typer.Option(None, "--ollama-host", help="Override OLLAMA_HOST"),
) -> None:
    """Start the streaming server + dashboard.

    Examples:
      gsd stream serve
      gsd stream serve --port 5009
    """
    legacy_serve_browser(
        host=host,
        port=port,
        log_level=log_level,
        json_logs=json_logs,
        text_logs=text_logs,
        llm_provider=llm_provider,
        llm_model=llm_model,
        ollama_host=ollama_host,
    )


@llm_app.callback()
def _llm_callback() -> None:
    """LLM/provider validation helpers.

    Examples:
      gsd llm --help
      gsd llm validate
    """


@llm_app.command("validate")
def llm_validate(
    llm_provider: str | None = typer.Option(
        None,
        "--llm-provider",
        help="LLM provider (anthropic, chatbrowseruse, openai, ollama)",
    ),
    llm_model: str | None = typer.Option(None, "--llm-model", help="Override LLM model name"),
    ollama_host: str | None = typer.Option(None, "--ollama-host", help="Override OLLAMA_HOST"),
) -> None:
    """Validate LLM provider configuration for browser-use.

    Examples:
      gsd llm validate
      gsd llm validate --llm-provider ollama --llm-model llama3.2
    """
    legacy_validate_llm(llm_provider=llm_provider, llm_model=llm_model, ollama_host=ollama_host)


@dev_app.callback()
def _dev_callback() -> None:
    """Developer/debug-only commands.

    Examples:
      gsd dev --help
      gsd dev diagnose
    """


@dev_app.command("diagnose")
def dev_diagnose() -> None:
    """Run lightweight environment diagnostics.

    Examples:
      gsd dev diagnose
    """
    legacy_diagnose()


@dev_app.command("echo")
def dev_echo(
    disable_echo: bool = typer.Option(
        False, "--no-echo", is_flag=True, help="Disable echoing stdin back to stdout"
    ),
    once: bool = typer.Option(
        False, "--once", is_flag=True, help="Process a single message then exit"
    ),
) -> None:
    """Start a tiny echo loop (debugging only).

    Examples:
      gsd dev echo --once
    """
    legacy_serve_echo(disable_echo=disable_echo, once=once)


@dev_app.command("smoke")
def dev_smoke() -> None:
    """Run a minimal runtime smoke (dashboard + screenshot storage).

    Examples:
      gsd dev smoke
    """
    legacy_smoke()
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
