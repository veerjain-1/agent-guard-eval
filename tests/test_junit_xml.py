"""JUnit reports must remain parseable when traces contain unusual strings."""

import json
from xml.etree import ElementTree

import pytest
from click.testing import CliRunner

from agentguard.cli import cli
from agentguard.models import EvaluationResult, Finding, Severity
from agentguard.reporters.junit import render_junit_report


@pytest.fixture
def result():
    return EvaluationResult(
        session_id="report-session",
        passed=False,
        total_checks=7,
        passed_checks=6,
        failed_checks=1,
        findings=[
            Finding(
                rule_id="AG-003-B",
                rule_name="Command injection",
                severity=Severity.CRITICAL,
                message="Unsafe command",
                step_id=1,
                tool_name="exec",
            )
        ],
    )


def test_trace_markup_remains_text_in_junit(result):
    result.session_id = 'session<&"'
    finding = result.findings[0]
    finding.tool_name = '</failure><testcase name="injected"/>&'
    finding.message = 'Command uses <input> & "quotes"'
    finding.details = {"payload": '<input>&"'}

    root = ElementTree.fromstring(render_junit_report(result))

    assert root.attrib["name"] == f"agentguard.{result.session_id}"
    assert len(root.findall("testcase")) == 7
    assert root.find("testcase[@name='injected']") is None
    failure = root.find(".//failure")
    assert failure.attrib["message"] == finding.message
    assert finding.tool_name in failure.text
    assert str(finding.details) in failure.text


@pytest.mark.parametrize("field", ["session_id", "message", "tool_name"])
def test_invalid_xml_characters_are_replaced(result, field):
    invalid = "\x00\x08\x0b\x0c\x1f\ud800\udfff\ufffe\uffff"
    target = result if field == "session_id" else result.findings[0]
    setattr(target, field, f"before{invalid}after")

    report = render_junit_report(result)
    root = ElementTree.fromstring(report.encode("utf-8"))

    assert root.tag == "testsuite"
    assert "before" + "\ufffd" * len(invalid) + "after" in report


def test_valid_unicode_and_xml_whitespace_are_preserved(result):
    result.findings[0].tool_name = "測試-é-🚀\tline\nnext\rfinal"

    root = ElementTree.fromstring(render_junit_report(result))

    assert "測試-é-🚀\tline\nnext\nfinal" in root.find(".//failure").text


def test_cli_junit_report_with_markup_in_tool_name(tmp_path):
    trace = tmp_path / "trace.json"
    report = tmp_path / "report.xml"
    tool = 'exec<&"'
    trace.write_text(
        json.dumps(
            {
                "session_id": "cli-junit",
                "tool_calls": [
                    {
                        "step_id": 1,
                        "tool_name": tool,
                        "arguments": {"cmd": "rm -rf /"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    outcome = CliRunner().invoke(
        cli, ["evaluate", str(trace), "--format", "junit", "-o", str(report)]
    )

    assert outcome.exit_code == 1
    root = ElementTree.fromstring(report.read_bytes())
    assert any(tool in failure.text for failure in root.findall(".//failure"))
