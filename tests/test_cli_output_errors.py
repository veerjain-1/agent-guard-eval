"""Regression tests for CLI report output write failures (issue #3)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from agentguard.cli import cli


@pytest.fixture
def valid_trace(tmp_path):
    path = tmp_path / "trace.json"
    path.write_text(
        json.dumps(
            {
                "session_id": "write-tests",
                "agent_name": "agent",
                "tool_calls": [
                    {
                        "step_id": 1,
                        "tool_name": "read",
                        "arguments": {"file": "doc.txt"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    ("command", "report_format"),
    [
        ("evaluate", "console"),
        ("evaluate", "junit"),
        ("evaluate", "sarif"),
        ("evaluate", "html"),
        ("fuzz", None),
        ("sanitize", None),
        ("diff", "console"),
        ("diff", "markdown"),
    ],
)
@pytest.mark.parametrize("failure", ["missing_parent", "permission_denied"])
def test_write_failures_have_actionable_errors(
    tmp_path, valid_trace, command, report_format, failure
):
    """Every command and report format exits 2 on an output write error."""
    output = (
        tmp_path / "missing" / "report.txt"
        if failure == "missing_parent"
        else tmp_path / "report.txt"
    )

    if command == "evaluate":
        args = ["evaluate", str(valid_trace), "--format", report_format]
    elif command == "fuzz":
        args = ["fuzz", "Translate this text to Spanish"]
    elif command == "sanitize":
        args = ["sanitize", str(valid_trace)]
    else:
        args = ["diff", str(valid_trace), str(valid_trace), "--format", report_format]

    args.extend(["--output", str(output)])
    runner = CliRunner()

    if failure == "permission_denied":
        with patch.object(
            Path, "write_text", side_effect=PermissionError("simulated access denied")
        ):
            result = runner.invoke(cli, args)
    else:
        result = runner.invoke(cli, args)

    assert result.exit_code == 2, result.output
    assert f"Error writing output file '{output}'" in result.output
    assert "Traceback (most recent call last)" not in result.output
    assert "written to " not in result.output.lower()
    assert "Saved " not in result.output
    assert not output.exists()


def test_diff_regression_still_exits_one_after_successful_write(tmp_path, valid_trace):
    """A genuine regression still exits 1 after its report was saved."""
    candidate = tmp_path / "candidate.json"
    candidate.write_text(
        json.dumps(
            {
                "session_id": "candidate",
                "agent_name": "agent",
                "tool_calls": [
                    {
                        "step_id": 1,
                        "tool_name": "exec",
                        "arguments": {"cmd": "rm -rf /"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report = tmp_path / "diff.md"

    result = CliRunner().invoke(
        cli,
        [
            "diff",
            str(valid_trace),
            str(candidate),
            "--format",
            "markdown",
            "--output",
            str(report),
        ],
    )

    assert result.exit_code == 1, result.output
    assert report.is_file()
    assert "REGRESSED" in report.read_text(encoding="utf-8")
