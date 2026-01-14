from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from gsd_browser import gsd_cli, legacy_cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner(mix_stderr=False)


def test_gsd_help_lists_groups_and_examples(runner: CliRunner) -> None:
    result = runner.invoke(gsd_cli.app, ["--help"])
    assert result.exit_code == 0, result.output
    assert "Examples:" in result.output
    for group in ("mcp", "config", "browser", "stream", "llm", "dev"):
        assert group in result.output


@pytest.mark.parametrize(
    "args",
    [
        ("mcp", "--help"),
        ("mcp", "tools", "--help"),
        ("config", "--help"),
        ("browser", "--help"),
        ("stream", "--help"),
        ("llm", "--help"),
        ("dev", "--help"),
    ],
)
def test_help_entry_points_include_examples(runner: CliRunner, args: tuple[str, ...]) -> None:
    result = runner.invoke(gsd_cli.app, list(args))
    assert result.exit_code == 0, result.output
    assert "Examples:" in result.output


def test_mcp_config_prints_gsd_command_and_args(runner: CliRunner, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    result = runner.invoke(
        gsd_cli.app,
        ["mcp", "config", "--format", "json"],
        env={"GSD_BROWSER_ENV_FILE": str(env_path)},
    )
    assert result.exit_code == 0, result.output
    assert '"command": "gsd"' in result.output
    assert '"args": [' in result.output
    assert '"mcp"' in result.output
    assert '"serve"' in result.output


def test_tool_policy_mutation_output_contract_and_parsing(
    runner: CliRunner, tmp_path: Path
) -> None:
    env_path = tmp_path / ".env"
    result = runner.invoke(
        gsd_cli.app,
        ["mcp", "tools", "deny", "get_screenshots,web-eval-agent"],
        env={"GSD_BROWSER_ENV_FILE": str(env_path)},
    )
    assert result.exit_code == 0, result.output

    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 4
    assert lines[0] == f"Updated: {env_path}"
    assert lines[1].startswith("GSD_BROWSER_MCP_ENABLED_TOOLS=")
    assert lines[2] == "GSD_BROWSER_MCP_DISABLED_TOOLS=get_screenshots,web_eval_agent"
    assert lines[3] == "Restart your MCP host/session"


def test_unknown_tool_exits_2_and_prints_known_list(runner: CliRunner, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    result = runner.invoke(
        gsd_cli.app,
        ["mcp", "tools", "disable", "not_a_tool"],
        env={"GSD_BROWSER_ENV_FILE": str(env_path)},
    )
    assert result.exit_code == 2
    assert "Known tools:" in result.stderr


def test_legacy_shim_warns_on_stderr_and_matches_exit_code(
    runner: CliRunner, tmp_path: Path
) -> None:
    env_path = tmp_path / ".env"
    env = {"GSD_BROWSER_ENV_FILE": str(env_path)}

    canonical_args = ["mcp", "tools", "deny", "get_screenshots"]
    legacy_args = ["mcp-tools", "set-disabled", "get_screenshots"]

    canonical_result = runner.invoke(gsd_cli.app, canonical_args, env=env)
    assert canonical_result.exit_code == 0, canonical_result.output

    if env_path.exists():
        env_path.unlink()

    legacy_result = runner.invoke(legacy_cli.app, legacy_args, env=env)
    assert legacy_result.exit_code == canonical_result.exit_code
    assert legacy_result.output == canonical_result.output
    assert "Deprecated: use 'gsd mcp tools deny get_screenshots'" in legacy_result.stderr
