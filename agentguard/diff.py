"""Behavioral and security regression diff engine for comparing agent execution traces."""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

from agentguard.engine import evaluate_trace
from agentguard.evaluators.base import BaseEvaluator
from agentguard.models import AgentTrace, Finding


def _finding_key(finding: Finding) -> tuple[str, str, str]:
    return finding.rule_id, finding.tool_name or "", finding.message


class DiffSummary(BaseModel):
    """Summary of behavioral and security changes between two agent traces."""

    baseline_session: str
    candidate_session: str
    baseline_steps: int
    candidate_steps: int
    steps_delta: int
    baseline_duration_ms: float
    candidate_duration_ms: float
    duration_delta_ms: float
    duration_delta_pct: float
    tool_counts_baseline: dict[str, int] = Field(default_factory=dict)
    tool_counts_candidate: dict[str, int] = Field(default_factory=dict)
    new_findings: list[Finding] = Field(default_factory=list)
    resolved_findings: list[Finding] = Field(default_factory=list)
    retained_findings: list[Finding] = Field(default_factory=list)
    verdict: str  # "REGRESSED" | "IMPROVED" | "UNCHANGED"


class TraceDiffEngine:
    """Computes behavioral shifts and guardrail regressions across agent trace versions."""

    def __init__(self, evaluators: list[BaseEvaluator] | None = None):
        self.evaluators = evaluators

    def compare(self, baseline: AgentTrace, candidate: AgentTrace) -> DiffSummary:
        """Compare a baseline trace with a candidate trace."""
        # 1. Evaluate both traces
        res_baseline = evaluate_trace(baseline, evaluators=self.evaluators)
        res_candidate = evaluate_trace(candidate, evaluators=self.evaluators)

        # 2. Step metrics
        base_steps = len(baseline.tool_calls)
        cand_steps = len(candidate.tool_calls)
        steps_delta = cand_steps - base_steps

        # 3. Latency metrics
        base_dur = sum(
            c.duration_ms for c in baseline.tool_calls if c.duration_ms is not None
        )
        cand_dur = sum(
            c.duration_ms for c in candidate.tool_calls if c.duration_ms is not None
        )
        dur_delta = cand_dur - base_dur
        dur_pct = (dur_delta / base_dur * 100.0) if base_dur > 0 else 0.0

        # 4. Tool usage distributions
        tool_counts_base: dict[str, int] = {}
        for c in baseline.tool_calls:
            tool_counts_base[c.tool_name] = tool_counts_base.get(c.tool_name, 0) + 1

        tool_counts_cand: dict[str, int] = {}
        for c in candidate.tool_calls:
            tool_counts_cand[c.tool_name] = tool_counts_cand.get(c.tool_name, 0) + 1

        # 5. Finding regressions
        # Match occurrences rather than distinct keys: repeating an existing
        # violation is a regression even when its rule/tool/message is unchanged.
        base_remaining = Counter(_finding_key(f) for f in res_baseline.findings)
        cand_remaining = Counter(_finding_key(f) for f in res_candidate.findings)

        new_findings: list[Finding] = []
        resolved_findings: list[Finding] = []
        retained_findings: list[Finding] = []
        for finding in res_candidate.findings:
            key = _finding_key(finding)
            if base_remaining[key] > 0:
                retained_findings.append(finding)
                base_remaining[key] -= 1
            else:
                new_findings.append(finding)

        for finding in res_baseline.findings:
            key = _finding_key(finding)
            if cand_remaining[key] > 0:
                cand_remaining[key] -= 1
            else:
                resolved_findings.append(finding)

        if new_findings:
            verdict = "REGRESSED"
        elif resolved_findings:
            verdict = "IMPROVED"
        else:
            verdict = "UNCHANGED"

        return DiffSummary(
            baseline_session=baseline.session_id,
            candidate_session=candidate.session_id,
            baseline_steps=base_steps,
            candidate_steps=cand_steps,
            steps_delta=steps_delta,
            baseline_duration_ms=round(base_dur, 2),
            candidate_duration_ms=round(cand_dur, 2),
            duration_delta_ms=round(dur_delta, 2),
            duration_delta_pct=round(dur_pct, 1),
            tool_counts_baseline=tool_counts_base,
            tool_counts_candidate=tool_counts_cand,
            new_findings=new_findings,
            resolved_findings=resolved_findings,
            retained_findings=retained_findings,
            verdict=verdict,
        )


def render_diff_console(diff: DiffSummary, console: Console | None = None) -> None:
    """Print an interactive terminal diff report using Rich."""
    console = console or Console()

    color_verdict = {
        "REGRESSED": "[bold red]REGRESSED ⚠️[/bold red]",
        "IMPROVED": "[bold green]IMPROVED ✨[/bold green]",
        "UNCHANGED": "[bold blue]UNCHANGED ⚖️[/bold blue]",
    }.get(diff.verdict, diff.verdict)

    console.print("\n[bold]AgentGuard Trace Comparison & Regression Audit[/bold]")
    console.print(f"Verdict: {color_verdict}\n")

    table = Table(title="Execution Metrics Comparison")
    table.add_column("Metric", style="cyan")
    table.add_column("Baseline", justify="right")
    table.add_column("Candidate", justify="right")
    table.add_column("Delta", justify="right")

    steps_delta_str = (
        f"+{diff.steps_delta}" if diff.steps_delta > 0 else str(diff.steps_delta)
    )
    table.add_row(
        "Total Steps",
        str(diff.baseline_steps),
        str(diff.candidate_steps),
        steps_delta_str,
    )

    dur_delta_str = (
        f"+{diff.duration_delta_ms:.1f}ms ({diff.duration_delta_pct:+.1f}%)"
        if diff.duration_delta_ms > 0
        else f"{diff.duration_delta_ms:.1f}ms ({diff.duration_delta_pct:+.1f}%)"
    )
    table.add_row(
        "Duration (ms)",
        f"{diff.baseline_duration_ms:.1f}ms",
        f"{diff.candidate_duration_ms:.1f}ms",
        dur_delta_str,
    )
    table.add_row(
        "New Findings (Regressions)",
        "0",
        str(len(diff.new_findings)),
        f"+{len(diff.new_findings)}" if diff.new_findings else "0",
    )
    table.add_row(
        "Resolved Findings",
        str(len(diff.resolved_findings)),
        "0",
        f"-{len(diff.resolved_findings)}" if diff.resolved_findings else "0",
    )
    console.print(table)

    if diff.new_findings:
        console.print(
            "\n[bold red]❌ Introduced Vulnerabilities / Guardrail Regressions:[/bold red]"
        )
        for f in diff.new_findings:
            console.print(
                f"  • [red][{f.severity}] {f.rule_id}[/red]: {f.message} (tool: {f.tool_name or 'N/A'})"
            )

    if diff.resolved_findings:
        console.print("\n[bold green]✔ Resolved Findings:[/bold green]")
        for f in diff.resolved_findings:
            console.print(f"  • [green][{f.severity}] {f.rule_id}[/green]: {f.message}")


def render_diff_markdown(diff: DiffSummary) -> str:
    """Generate Markdown summary table for GitHub PR comments and CI summaries."""
    lines: list[str] = [
        "### 🛡️ AgentGuard Trace Regression Report",
        "",
        f"**Verdict**: **`{diff.verdict}`** | Baseline: `{diff.baseline_session}` ➔ Candidate: `{diff.candidate_session}`",
        "",
        "| Metric | Baseline | Candidate | Delta |",
        "| :--- | :---: | :---: | :---: |",
        f"| **Tool Steps** | {diff.baseline_steps} | {diff.candidate_steps} | `{diff.steps_delta:+d}` |",
        f"| **Execution Time** | {diff.baseline_duration_ms:.1f}ms | {diff.candidate_duration_ms:.1f}ms | `{diff.duration_delta_ms:+.1f}ms ({diff.duration_delta_pct:+.1f}%)` |",
        f"| **New Regressions** | 0 | {len(diff.new_findings)} | `+{len(diff.new_findings)}` |",
        f"| **Resolved Findings** | {len(diff.resolved_findings)} | 0 | `-{len(diff.resolved_findings)}` |",
        "",
    ]

    if diff.new_findings:
        lines.append("#### ❌ Regressions Introduced")
        for f in diff.new_findings:
            lines.append(
                f"- **[{f.severity}] {f.rule_id}**: {f.message} (Tool: `{f.tool_name}`)"
            )
        lines.append("")

    if diff.resolved_findings:
        lines.append("#### ✅ Violations Resolved")
        for f in diff.resolved_findings:
            lines.append(f"- **[{f.severity}] {f.rule_id}**: {f.message}")
        lines.append("")

    return "\n".join(lines)
