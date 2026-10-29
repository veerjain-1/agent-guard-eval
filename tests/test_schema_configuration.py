"""Invalid schema configuration must not masquerade as a trace finding."""

import json

import pytest
from click.testing import CliRunner

from agentguard.cli import cli
from agentguard.evaluators.schema_validator import SchemaValidator
from agentguard.models import AgentTrace, ToolCall


@pytest.mark.parametrize("schemas", [[], ["fetch"], "fetch", 7, False, None])
def test_cli_rejects_non_object_schema_maps(tmp_path, schemas):
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(
        '{"session_id":"config-test","tool_calls":[]}', encoding="utf-8"
    )
    schema_path = tmp_path / "schemas.json"
    schema_path.write_text(json.dumps(schemas), encoding="utf-8")

    result = CliRunner().invoke(
        cli, ["evaluate", str(trace_path), "-s", str(schema_path)]
    )

    assert result.exit_code == 2
    assert "Error reading schema file" in result.output
    assert "object mapping tool names" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    "schema", [{"type": "not-a-type"}, {"required": "name"}, 17, None]
)
def test_cli_rejects_invalid_unused_tool_schema(tmp_path, schema):
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(
        '{"session_id":"config-test","tool_calls":[]}', encoding="utf-8"
    )
    schema_path = tmp_path / "schemas.json"
    schema_path.write_text(json.dumps({"fetch": schema}), encoding="utf-8")

    result = CliRunner().invoke(
        cli, ["evaluate", str(trace_path), "-s", str(schema_path)]
    )

    assert result.exit_code == 2
    assert "Invalid JSON schema for tool 'fetch'" in result.output
    assert "Traceback" not in result.output


def test_invalid_assignment_preserves_existing_schemas():
    validator = SchemaValidator({"fetch": {"type": "object"}})
    with pytest.raises(ValueError, match="Invalid JSON schema for tool 'fetch'"):
        validator.tool_schemas = {"fetch": {"type": "invalid"}}
    assert validator.tool_schemas == {"fetch": {"type": "object"}}


def test_invalid_registration_does_not_replace_existing_schema():
    validator = SchemaValidator({"fetch": {"type": "object"}})
    with pytest.raises(ValueError, match="Invalid JSON schema for tool 'fetch'"):
        validator.register_schema("fetch", {"type": "invalid"})
    assert validator.tool_schemas == {"fetch": {"type": "object"}}


@pytest.mark.parametrize("schemas", [[], ["fetch"], "fetch", 0, False])
def test_constructor_rejects_non_object_maps(schemas):
    with pytest.raises(TypeError, match="object mapping tool names"):
        SchemaValidator(schemas)


@pytest.mark.parametrize("schema,expected_findings", [(True, 0), (False, 1)])
def test_boolean_tool_schemas_remain_supported(schema, expected_findings):
    validator = SchemaValidator({"fetch": schema})
    trace = AgentTrace(
        session_id="boolean-schema",
        tool_calls=[ToolCall(step_id=1, tool_name="fetch", arguments={})],
    )
    assert len(validator.evaluate(trace)) == expected_findings


@pytest.mark.parametrize("arguments,expected_exit", [({"q": "test"}, 0), ({}, 1)])
def test_valid_cli_schema_preserves_finding_exit_code(
    tmp_path, arguments, expected_exit
):
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(
        json.dumps(
            {
                "session_id": "config-test",
                "tool_calls": [
                    {"step_id": 1, "tool_name": "fetch", "arguments": arguments}
                ],
            }
        ),
        encoding="utf-8",
    )
    schema_path = tmp_path / "schemas.json"
    schema_path.write_text(
        json.dumps(
            {
                "fetch": {
                    "type": "object",
                    "required": ["q"],
                    "properties": {"q": {"type": "string"}},
                }
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cli, ["evaluate", str(trace_path), "-s", str(schema_path)]
    )

    assert result.exit_code == expected_exit
    assert "Error reading schema file" not in result.output
