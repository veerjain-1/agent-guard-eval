"""Schema adherence and hallucinated tool validator."""

from typing import Any

import jsonschema

from agentguard.evaluators.base import BaseEvaluator
from agentguard.models import AgentTrace, Finding, Severity


class SchemaValidator(BaseEvaluator):
    """Detects schema non-conformance, undeclared tools, and hallucinated arguments."""

    rule_id = "AG-001"
    rule_name = "Tool Schema Adherence"

    def __init__(self, tool_schemas: dict[str, dict[str, Any] | bool] | None = None):
        """
        Args:
            tool_schemas: Dictionary mapping tool names to their JSON Schema definitions.
        """
        self.tool_schemas = {} if tool_schemas is None else tool_schemas

    @property
    def tool_schemas(self) -> dict[str, dict[str, Any] | bool]:
        return self._tool_schemas

    @tool_schemas.setter
    def tool_schemas(self, schemas: dict[str, dict[str, Any] | bool]) -> None:
        if not isinstance(schemas, dict):
            raise TypeError("Expected a JSON object mapping tool names to JSON schemas")
        for tool_name, schema in schemas.items():
            self._validate_schema(tool_name, schema)
        # Validate the entire configuration before replacing a working map.
        self._tool_schemas = dict(schemas)

    @staticmethod
    def _validate_schema(tool_name: str, schema: dict[str, Any] | bool) -> None:
        if not isinstance(tool_name, str):
            raise TypeError("Tool schema names must be strings")
        try:
            jsonschema.Draft7Validator.check_schema(schema)
        except jsonschema.SchemaError as exc:
            raise ValueError(
                f"Invalid JSON schema for tool '{tool_name}': {exc.message}"
            ) from exc

    def register_schema(self, tool_name: str, schema: dict[str, Any] | bool) -> None:
        """Register a JSON schema definition for a tool."""
        self._validate_schema(tool_name, schema)
        self.tool_schemas[tool_name] = schema

    def evaluate(self, trace: AgentTrace) -> list[Finding]:
        findings: list[Finding] = []

        if not self.tool_schemas:
            # If no schemas are configured, skip strict schema checks
            return findings

        for call in trace.tool_calls:
            # 1. Check if tool is known/declared
            if call.tool_name not in self.tool_schemas:
                findings.append(
                    Finding(
                        rule_id="AG-001-A",
                        rule_name=f"{self.rule_name}: Undeclared Tool",
                        severity=Severity.HIGH,
                        message=f"Agent invoked undeclared/hallucinated tool: '{call.tool_name}'",
                        step_id=call.step_id,
                        tool_name=call.tool_name,
                        details={"tool_name": call.tool_name},
                    )
                )
                continue

            schema = self.tool_schemas[call.tool_name]
            validator = jsonschema.Draft7Validator(schema)

            # 2. Check schema conformance
            errors = list(validator.iter_errors(call.arguments))
            for err in errors:
                findings.append(
                    Finding(
                        rule_id="AG-001-B",
                        rule_name=f"{self.rule_name}: Schema Drift",
                        severity=Severity.HIGH
                        if err.validator == "required"
                        else Severity.MEDIUM,
                        message=f"Tool '{call.tool_name}' argument error: {err.message}",
                        step_id=call.step_id,
                        tool_name=call.tool_name,
                        details={
                            "validator": err.validator,
                            "path": list(err.path),
                            "schema_path": list(err.schema_path),
                        },
                    )
                )

        return findings
