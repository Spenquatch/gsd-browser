"""Prompt comparison harness: Extended vs Override-Enhanced system prompts.

This harness runs 3 test scenarios (simple, medium, high complexity) twice each:
1. First run: Extended prompt (current A1 approach)
2. Second run: Override-enhanced prompt (triple reinforcement + early placement)

Each scenario uses 4x timeout lengths to avoid timeout failures and isolate
schema compliance issues.

Target model: Claude Haiku 4.5 (known 50% pass rate with extended prompt)
Goal: Test if override-enhanced prompt improves Haiku's schema compliance

See: artifacts/real_world_sanity/SYSTEM_PROMPT_OVERRIDE_PROPOSAL.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gsd_browser.config import load_settings
from gsd_browser.mcp_server import web_eval_agent


@dataclass(frozen=True)
class Scenario:
    id: str
    url: str
    task: str
    complexity: str  # "simple", "medium", "high"
    mode: str = "compact"
    headless_browser: bool = True


# Selected scenarios covering simple → medium → high complexity
COMPARISON_SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        id="wikipedia-openai-simple",
        url="https://en.wikipedia.org/wiki/OpenAI",
        task=(
            "Find the first paragraph of this article and return the first sentence. "
            "Also return the final URL of the page you used."
        ),
        complexity="simple",
    ),
    Scenario(
        id="hackernews-top-story-medium",
        url="https://news.ycombinator.com/",
        task=(
            "Return the title and direct URL of the first story on the page. "
            "Do not include comment links."
        ),
        complexity="medium",
    ),
    Scenario(
        id="npm-deep-research-high",
        url="https://www.npmjs.com/package/playwright",
        task=(
            "From the playwright package page: (1) Note the weekly download count. "
            "(2) Find and click the 'Repository' link to go to GitHub. (3) On GitHub, find the "
            "number of stars. (4) Click on the 'Issues' tab. (5) Count the number of open issues "
            "(look for the count in the UI). (6) Return: package name, weekly downloads, GitHub "
            "stars, and open issues count."
        ),
        complexity="high",
    ),
)


@dataclass
class TestRun:
    scenario_id: str
    prompt_mode: str  # "extend" or "override"
    status: str  # "pass", "soft_fail", "hard_fail"
    validation_errors: int
    execution_time_s: float
    step_count: int
    text_result: str
    error_summary: str | None
    artifacts_path: str | None


def _now_slug() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime())


def _write_json(path: Path, payload: Any, *, sort_keys: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=sort_keys),
        encoding="utf-8",
    )


def _count_validation_errors(events: list[dict[str, Any]]) -> int:
    """Count validation/schema errors in agent events."""
    count = 0
    for event in events:
        summary = event.get("summary", "")
        if not summary:
            continue
        if "schema_validation" in summary.lower() or "validation error" in summary.lower():
            count += 1
    return count


async def run_scenario_with_prompt_mode(
    scenario: Scenario,
    prompt_mode: str,
    *,
    step_timeout_s: float,
    budget_s: float,
    artifacts_base: Path,
) -> TestRun:
    """Run a single scenario with specified prompt mode.

    Args:
        scenario: Test scenario to run
        prompt_mode: "extend" or "override"
        step_timeout_s: Step timeout (4x default for Haiku)
        budget_s: Budget timeout (4x default for Haiku)
        artifacts_base: Base directory for artifacts

    Returns:
        TestRun with results
    """
    # Set environment variable for prompt mode
    if prompt_mode == "override":
        os.environ["GSD_OVERRIDE_SYSTEM_PROMPT"] = "1"
    else:
        os.environ["GSD_OVERRIDE_SYSTEM_PROMPT"] = "0"

    print(f"\n{'='*80}")
    print(f"Running: {scenario.id} (complexity: {scenario.complexity})")
    print(f"Prompt mode: {prompt_mode}")
    print(f"Timeouts: step={step_timeout_s}s, budget={budget_s}s")
    print(f"{'='*80}\n")

    start_time = time.time()

    try:
        # Create dummy context (required by web_eval_agent)
        ctx = Context()

        # Run scenario
        result_contents = await web_eval_agent(
            url=scenario.url,
            task=scenario.task,
            ctx=ctx,
            headless_browser=scenario.headless_browser,
            mode=scenario.mode,
            step_timeout_s=step_timeout_s,
            budget_s=budget_s,
        )

        execution_time = time.time() - start_time

        # Extract result text
        text_result = ""
        for content in result_contents:
            if hasattr(content, "text"):
                text_result = content.text
                break

        # Parse session payload from result
        session_payload: dict[str, Any] = {}
        try:
            # Try parsing as direct JSON first (new format)
            session_payload = json.loads(text_result)
        except (ValueError, json.JSONDecodeError):
            # Fallback: try extracting JSON from markdown code block (old format)
            if text_result.startswith("Session "):
                try:
                    json_start = text_result.index("```json\n") + 8
                    json_end = text_result.index("\n```", json_start)
                    session_payload = json.loads(text_result[json_start:json_end])
                except (ValueError, json.JSONDecodeError):
                    pass

        # Load events.json to count validation errors
        validation_errors = 0
        step_count = 0
        artifacts_path = session_payload.get("artifacts_path")
        if artifacts_path:
            events_path = Path(artifacts_path) / "events.json"
            if events_path.exists():
                events = json.loads(events_path.read_text(encoding="utf-8"))
                validation_errors = _count_validation_errors(events)
                step_count = len([e for e in events if e.get("step") is not None])

        # Classify result (using new v1 format)
        task_status = session_payload.get("status", "unknown")
        if task_status == "success":
            status = "pass"
        elif artifacts_path and Path(artifacts_path).exists():
            # Failed but has artifacts
            has_events = (Path(artifacts_path) / "events.json").exists()
            has_screenshots = len(list(Path(artifacts_path).glob("screenshot_*.png"))) > 0
            status = "soft_fail" if (has_events or has_screenshots) else "hard_fail"
        else:
            status = "hard_fail"

        # Extract error summary if failed
        error_summary = None
        if status != "pass":
            # Try to get error from summary or result
            error_summary = session_payload.get(
                "summary", session_payload.get("result", "Unknown error")
            )
            if not error_summary or error_summary == "null":
                error_summary = "Task failed"

        return TestRun(
            scenario_id=scenario.id,
            prompt_mode=prompt_mode,
            status=status,
            validation_errors=validation_errors,
            execution_time_s=round(execution_time, 2),
            step_count=step_count,
            text_result=text_result[:500],  # Truncate for report
            error_summary=error_summary,
            artifacts_path=artifacts_path,
        )

    except Exception as exc:
        execution_time = time.time() - start_time
        return TestRun(
            scenario_id=scenario.id,
            prompt_mode=prompt_mode,
            status="hard_fail",
            validation_errors=0,
            execution_time_s=round(execution_time, 2),
            step_count=0,
            text_result="",
            error_summary=f"Exception: {type(exc).__name__}: {exc}",
            artifacts_path=None,
        )


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare extended vs override-enhanced system prompts"
    )
    parser.add_argument(
        "--model",
        default="claude-haiku-4-5",
        help="Model to use (default: claude-haiku-4-5)",
    )
    parser.add_argument(
        "--step-timeout",
        type=float,
        default=60.0,
        help="Step timeout in seconds (default: 60.0 = 4x Haiku default)",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=240.0,
        help="Budget timeout in seconds (default: 240.0 = 4x Haiku default)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/prompt_comparison"),
        help="Output directory for results",
    )

    args = parser.parse_args()

    # Override model setting
    os.environ["GSD_MODEL"] = args.model

    # Load settings
    settings = load_settings()
    print(f"Using model: {settings.model}")
    print(f"Step timeout: {args.step_timeout}s")
    print(f"Budget timeout: {args.budget}s")
    print(f"Scenarios: {len(COMPARISON_SCENARIOS)}")

    # Create output directory
    run_slug = _now_slug()
    output_dir = args.output_dir / run_slug
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nResults will be saved to: {output_dir}\n")

    # Run all scenarios with both prompt modes
    all_runs: list[TestRun] = []

    for scenario in COMPARISON_SCENARIOS:
        # Run with extended prompt (current approach)
        run_extend = await run_scenario_with_prompt_mode(
            scenario,
            prompt_mode="extend",
            step_timeout_s=args.step_timeout,
            budget_s=args.budget,
            artifacts_base=output_dir,
        )
        all_runs.append(run_extend)

        # Small delay between runs
        await asyncio.sleep(2)

        # Run with override-enhanced prompt
        run_override = await run_scenario_with_prompt_mode(
            scenario,
            prompt_mode="override",
            step_timeout_s=args.step_timeout,
            budget_s=args.budget,
            artifacts_base=output_dir,
        )
        all_runs.append(run_override)

        # Delay between scenarios
        await asyncio.sleep(2)

    # Generate comparison report
    report = generate_comparison_report(all_runs, args)

    # Save results
    results_file = output_dir / "comparison_results.json"
    _write_json(
        results_file,
        {
            "run_id": run_slug,
            "model": settings.model,
            "step_timeout_s": args.step_timeout,
            "budget_s": args.budget,
            "scenarios": len(COMPARISON_SCENARIOS),
            "runs": [asdict(run) for run in all_runs],
            "report": report,
        },
        sort_keys=False,
    )

    # Save markdown report
    report_file = output_dir / "COMPARISON_REPORT.md"
    report_file.write_text(report, encoding="utf-8")

    print(f"\n{'='*80}")
    print(f"Results saved to: {output_dir}")
    print(f"{'='*80}\n")
    print(report)

    # Return 0 if all tests passed, 1 otherwise
    pass_count = sum(1 for run in all_runs if run.status == "pass")
    return 0 if pass_count == len(all_runs) else 1


def generate_comparison_report(runs: list[TestRun], args: argparse.Namespace) -> str:
    """Generate markdown comparison report."""
    lines = [
        "# Prompt Comparison Report: Extended vs Override-Enhanced",
        "",
        f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
        f"**Model:** {args.model}",
        f"**Timeouts:** Step={args.step_timeout}s, Budget={args.budget}s (4x default)",
        "",
        "## Summary",
        "",
    ]

    # Group runs by prompt mode
    extend_runs = [r for r in runs if r.prompt_mode == "extend"]
    override_runs = [r for r in runs if r.prompt_mode == "override"]

    # Calculate statistics
    def calc_stats(mode_runs: list[TestRun]) -> dict[str, Any]:
        pass_count = sum(1 for r in mode_runs if r.status == "pass")
        validation_errors = sum(r.validation_errors for r in mode_runs)
        avg_time = sum(r.execution_time_s for r in mode_runs) / len(mode_runs) if mode_runs else 0
        avg_steps = sum(r.step_count for r in mode_runs) / len(mode_runs) if mode_runs else 0

        return {
            "pass_count": pass_count,
            "pass_rate": f"{(pass_count / len(mode_runs) * 100):.1f}%" if mode_runs else "0%",
            "validation_errors": validation_errors,
            "avg_time_s": round(avg_time, 2),
            "avg_steps": round(avg_steps, 1),
        }

    extend_stats = calc_stats(extend_runs)
    override_stats = calc_stats(override_runs)

    # Summary table
    lines.extend([
        "| Metric | Extended Prompt | Override-Enhanced Prompt |",
        "|--------|-----------------|--------------------------|",
        (
            f"| Pass Rate | {extend_stats['pass_rate']} "
            f"({extend_stats['pass_count']}/{len(extend_runs)}) | "
            f"{override_stats['pass_rate']} "
            f"({override_stats['pass_count']}/{len(override_runs)}) |"
        ),
        (
            f"| Validation Errors | {extend_stats['validation_errors']} | "
            f"{override_stats['validation_errors']} |"
        ),
        f"| Avg Execution Time | {extend_stats['avg_time_s']}s | {override_stats['avg_time_s']}s |",
        f"| Avg Steps | {extend_stats['avg_steps']} | {override_stats['avg_steps']} |",
        "",
    ])

    # Interpretation
    improvement = override_stats['pass_count'] - extend_stats['pass_count']
    error_reduction = extend_stats['validation_errors'] - override_stats['validation_errors']

    lines.extend([
        "## Interpretation",
        "",
        f"**Pass Rate Change:** {'+' if improvement > 0 else ''}{improvement} scenarios",
        (
            f"**Validation Error Change:** "
            f"{'-' if error_reduction > 0 else '+'}{abs(error_reduction)} errors"
        ),
        "",
    ])

    if improvement > 0:
        lines.append(
            f"✅ **Override-enhanced prompt improved pass rate by {improvement} scenarios**"
        )
    elif improvement < 0:
        lines.append(
            f"❌ **Override-enhanced prompt reduced pass rate by {abs(improvement)} scenarios**"
        )
    else:
        lines.append("➖ **No change in pass rate between prompt modes**")

    lines.append("")

    if error_reduction > 0:
        lines.append(
            f"✅ **Override-enhanced prompt reduced validation errors by {error_reduction}**"
        )
    elif error_reduction < 0:
        lines.append(
            f"❌ **Override-enhanced prompt increased validation errors by {abs(error_reduction)}**"
        )
    else:
        lines.append("➖ **No change in validation errors between prompt modes**")

    lines.extend([
        "",
        "## Detailed Results",
        "",
    ])

    # Group results by scenario for side-by-side comparison
    scenarios = {r.scenario_id for r in runs}
    for scenario_id in sorted(scenarios):
        extend_run = next((r for r in extend_runs if r.scenario_id == scenario_id), None)
        override_run = next((r for r in override_runs if r.scenario_id == scenario_id), None)

        if not extend_run or not override_run:
            continue

        # Determine complexity from scenario_id
        complexity = "unknown"
        if "simple" in scenario_id:
            complexity = "Simple"
        elif "medium" in scenario_id:
            complexity = "Medium"
        elif "high" in scenario_id:
            complexity = "High"

        lines.extend([
            f"### {scenario_id} ({complexity})",
            "",
            "| Metric | Extended | Override-Enhanced |",
            "|--------|----------|-------------------|",
            f"| Status | {extend_run.status} | {override_run.status} |",
            (
                f"| Validation Errors | {extend_run.validation_errors} | "
                f"{override_run.validation_errors} |"
            ),
            (
                f"| Execution Time | {extend_run.execution_time_s}s | "
                f"{override_run.execution_time_s}s |"
            ),
            f"| Steps | {extend_run.step_count} | {override_run.step_count} |",
            "",
        ])

        # Show errors if any
        if extend_run.error_summary or override_run.error_summary:
            lines.extend([
                "**Errors:**",
                "",
            ])
            if extend_run.error_summary:
                lines.append(f"- Extended: {extend_run.error_summary}")
            if override_run.error_summary:
                lines.append(f"- Override: {override_run.error_summary}")
            lines.append("")

    # Conclusion
    lines.extend([
        "## Conclusion",
        "",
    ])

    if override_stats['pass_count'] > extend_stats['pass_count']:
        lines.extend([
            f"The override-enhanced prompt **improved reliability** for {args.model}:",
            (
                f"- Pass rate increased from {extend_stats['pass_rate']} to "
                f"{override_stats['pass_rate']}"
            ),
            (
                f"- Validation errors reduced from {extend_stats['validation_errors']} to "
                f"{override_stats['validation_errors']}"
            ),
            "",
            (
                "**Hypothesis validated:** Triple reinforcement + early placement improves schema "
                "compliance."
            ),
        ])
    elif override_stats['pass_count'] == extend_stats['pass_count']:
        lines.extend([
            f"The override-enhanced prompt showed **no improvement** for {args.model}:",
            f"- Pass rate unchanged at {extend_stats['pass_rate']}",
            (
                f"- Validation errors: {extend_stats['validation_errors']} vs "
                f"{override_stats['validation_errors']}"
            ),
            "",
            "**Hypothesis not validated:** Enhanced prompt did not improve schema compliance.",
        ])
    else:
        lines.extend([
            f"The override-enhanced prompt **reduced reliability** for {args.model}:",
            (
                f"- Pass rate decreased from {extend_stats['pass_rate']} to "
                f"{override_stats['pass_rate']}"
            ),
            "",
            "**Unexpected result:** Enhanced prompt may have introduced confusion or overhead.",
        ])

    return "\n".join(lines)


if __name__ == "__main__":
    import asyncio

    # Run main async function
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
