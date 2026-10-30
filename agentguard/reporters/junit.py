"""JUnit XML reporter for CI test runner integration."""

import html
import re

from agentguard.models import EvaluationResult, Finding

_INVALID_XML_CHARACTERS = re.compile(
    "[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]"
)


def _escape_xml(text: str) -> str:
    """Escape markup and replace characters forbidden by XML 1.0."""
    return html.escape(_INVALID_XML_CHARACTERS.sub("\ufffd", text))


def render_junit_report(result: EvaluationResult) -> str:
    """Generates standard JUnit XML string from EvaluationResult."""
    testsuite_name = f"agentguard.{result.session_id}"
    tests_count = result.total_checks
    failures_count = result.failed_checks
    time_sec = result.duration_ms / 1000.0

    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<testsuite name="{_escape_xml(testsuite_name)}" tests="{tests_count}" failures="{failures_count}" errors="0" time="{time_sec:.3f}">',
    ]

    # Map findings by rule prefix
    findings_by_rule = {}
    for f in result.findings:
        prefix = f.rule_id.split("-")[0] + "-" + f.rule_id.split("-")[1]
        findings_by_rule.setdefault(prefix, []).append(f)

    # Standard checks
    standard_rules = [
        ("AG-001", "ToolSchemaAdherence"),
        ("AG-002", "RunawayLoopAndStateThrashing"),
        ("AG-003", "SecurityAndVulnerabilityGuard"),
        ("AG-004", "SSRFAndCloudMetadataGuard"),
        ("AG-005", "TokenBudgetAndContextBloatGuard"),
        ("AG-006", "LatencyAndSLAGuard"),
        ("AG-007", "TaintFlowAndIndirectInjectionGuard"),
    ]

    for rule_id, rule_name in standard_rules:
        rule_findings: list[Finding] = findings_by_rule.get(rule_id, [])
        lines.append(
            f'  <testcase classname="AgentGuard" name="{rule_name}" time="0.001">'
        )
        if rule_findings:
            for rf in rule_findings:
                msg = _escape_xml(rf.message)
                details = _escape_xml(str(rf.details))
                tool = _escape_xml(str(rf.tool_name))
                lines.append(
                    f'    <failure message="{msg}" type="{rf.severity.value}">'
                    f"{msg}\nDetails: {details}\nStep: {rf.step_id}\nTool: {tool}"
                    f"</failure>"
                )
        lines.append("  </testcase>")

    lines.append("</testsuite>")
    return "\n".join(lines)
