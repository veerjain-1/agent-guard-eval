"""Repeated findings must remain visible to the regression gate."""

import pytest
from click.testing import CliRunner

from agentguard.cli import cli
from agentguard.diff import TraceDiffEngine
from agentguard.evaluators.security_guard import SecurityGuard
from agentguard.models import AgentTrace, ToolCall


def trace(session, commands):
    return AgentTrace(
        session_id=session,
        tool_calls=[
            ToolCall(step_id=i, tool_name="exec", arguments={"cmd": command})
            for i, command in enumerate(commands, 1)
        ],
    )


@pytest.mark.parametrize(
    "before,after,verdict,new,resolved,retained",
    [
        (0, 2, "REGRESSED", 2, 0, 0),
        (1, 2, "REGRESSED", 1, 0, 1),
        (2, 1, "IMPROVED", 0, 1, 1),
        (2, 2, "UNCHANGED", 0, 0, 2),
        (2, 0, "IMPROVED", 0, 2, 0),
    ],
)
def test_repeated_findings_are_matched_one_to_one(
    before, after, verdict, new, resolved, retained
):
    baseline = trace("baseline", ["rm -rf /"] * before)
    candidate = trace("candidate", ["rm -rf /"] * after)

    diff = TraceDiffEngine([SecurityGuard()]).compare(baseline, candidate)

    assert diff.verdict == verdict
    assert len(diff.new_findings) == new
    assert len(diff.resolved_findings) == resolved
    assert len(diff.retained_findings) == retained
    if before == 1 and after == 2:
        assert diff.retained_findings[0].step_id == 1
        assert diff.new_findings[0].step_id == 2
    if before == 2 and after == 1:
        assert diff.resolved_findings[0].step_id == 2


def test_removed_finding_does_not_hide_an_added_repeat():
    baseline = trace("baseline", ["rm -rf /", "cat /etc/passwd"])
    candidate = trace("candidate", ["rm -rf /", "rm -rf /"])

    diff = TraceDiffEngine([SecurityGuard()]).compare(baseline, candidate)

    assert diff.verdict == "REGRESSED"
    assert [f.rule_id for f in diff.new_findings] == ["AG-003-B"]
    assert [f.rule_id for f in diff.resolved_findings] == ["AG-003-A"]


def test_reordering_steps_does_not_create_new_findings():
    baseline = trace("baseline", ["rm -rf /", "cat /etc/passwd"])
    candidate = trace("candidate", ["cat /etc/passwd", "rm -rf /"])

    diff = TraceDiffEngine([SecurityGuard()]).compare(baseline, candidate)

    assert diff.verdict == "UNCHANGED"
    assert not diff.new_findings
    assert not diff.resolved_findings
    assert [f.rule_id for f in diff.retained_findings] == ["AG-003-A", "AG-003-B"]


def test_cli_fails_when_an_existing_violation_is_repeated(tmp_path):
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(
        trace("baseline", ["rm -rf /"]).model_dump_json(), encoding="utf-8"
    )
    candidate.write_text(
        trace("candidate", ["rm -rf /", "rm -rf /"]).model_dump_json(), encoding="utf-8"
    )

    result = CliRunner().invoke(
        cli, ["diff", str(baseline), str(candidate), "--format", "markdown"]
    )

    assert result.exit_code == 1
    assert "REGRESSED" in result.output
    assert "AG-003-B" in result.output
