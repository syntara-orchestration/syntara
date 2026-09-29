"""Tests for the mcp_tool node parameter model and its discriminated node class."""

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from syntara.workflows.models.workflow_definition import MCPToolNode, WorkflowDefinition
from syntara.workflows.workflow_engine.models.workflow_definition import (
    MCP_TOOL_MAX_TIMEOUT_SECONDS,
    ActivityName,
    MCPToolExecutorParameters,
    MCPToolOutput,
    NodeType,
)


def _params(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    base: dict[str, Any] = {"integration_id": str(uuid4()), "tool_name": "echo"}
    base.update(overrides)
    return base


class TestMCPToolExecutorParameters:
    """Parameter model validation."""

    def test_minimal_parameters_default_arguments_to_empty_dict(self) -> None:
        config = MCPToolExecutorParameters.model_validate(_params())
        assert config.arguments == {}
        assert config.timeout_seconds is None

    def test_arguments_accept_nested_values_and_templates(self) -> None:
        config = MCPToolExecutorParameters.model_validate(
            _params(arguments={"msg": "${trigger.text}", "nested": {"items": [1, "${node_a.value}"]}})
        )
        assert config.arguments["msg"] == "${trigger.text}"
        assert config.arguments["nested"]["items"][1] == "${node_a.value}"

    def test_rejects_non_uuid_integration_id(self) -> None:
        with pytest.raises(ValidationError):
            MCPToolExecutorParameters.model_validate(_params(integration_id="not-a-uuid"))

    def test_accepts_template_integration_id(self) -> None:
        config = MCPToolExecutorParameters.model_validate(_params(integration_id="${trigger.integration_id}"))
        assert config.integration_id == "${trigger.integration_id}"

    def test_rejects_empty_tool_name(self) -> None:
        with pytest.raises(ValidationError):
            MCPToolExecutorParameters.model_validate(_params(tool_name=""))

    def test_rejects_blank_tool_name(self) -> None:
        with pytest.raises(ValidationError):
            MCPToolExecutorParameters.model_validate(_params(tool_name="   "))

    def test_rejects_missing_tool_name(self) -> None:
        with pytest.raises(ValidationError):
            MCPToolExecutorParameters.model_validate({"integration_id": str(uuid4())})

    def test_rejects_timeout_above_limit(self) -> None:
        with pytest.raises(ValidationError):
            MCPToolExecutorParameters.model_validate(_params(timeout_seconds=MCP_TOOL_MAX_TIMEOUT_SECONDS + 1))

    def test_rejects_zero_timeout(self) -> None:
        with pytest.raises(ValidationError):
            MCPToolExecutorParameters.model_validate(_params(timeout_seconds=0))

    def test_accepts_timeout_at_limit(self) -> None:
        config = MCPToolExecutorParameters.model_validate(_params(timeout_seconds=MCP_TOOL_MAX_TIMEOUT_SECONDS))
        assert config.timeout_seconds == MCP_TOOL_MAX_TIMEOUT_SECONDS


class TestMCPToolNodeDiscrimination:
    """The workflow definition must discriminate type='mcp_tool' to MCPToolNode."""

    def _definition(self, **param_overrides: Any) -> dict[str, Any]:  # noqa: ANN401
        return {
            "schema_version": "2.0.0",
            "name": "wf",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "mcp_tool", "parameters": _params(**param_overrides)}],
            "edges": [{"from": "t1", "to": "n1"}],
        }

    def test_definition_resolves_to_mcp_tool_node(self) -> None:
        definition = WorkflowDefinition.model_validate(self._definition())
        node = definition.nodes[0]
        assert isinstance(node, MCPToolNode)
        assert node.type == NodeType.MCP_TOOL.value

    def test_definition_round_trips_through_dump(self) -> None:
        definition = WorkflowDefinition.model_validate(self._definition(arguments={"a": 1}))
        # Matches _definition_to_dict() in workflows/router.py
        dumped = definition.model_dump(exclude_defaults=True)
        assert dumped["nodes"][0]["type"] == "mcp_tool"
        assert dumped["nodes"][0]["parameters"]["arguments"] == {"a": 1}
        assert WorkflowDefinition.model_validate(dumped).nodes[0].type == "mcp_tool"

    def test_invalid_parameters_rejected_through_the_union(self) -> None:
        definition = self._definition()
        definition["nodes"][0]["parameters"]["tool_name"] = ""
        with pytest.raises(ValidationError):
            WorkflowDefinition.model_validate(definition)

    def test_settings_accept_timeout(self) -> None:
        definition = self._definition()
        definition["nodes"][0]["settings"] = {"timeout": 45}
        node = WorkflowDefinition.model_validate(definition).nodes[0]
        assert isinstance(node, MCPToolNode)
        assert node.settings is not None
        assert node.settings.timeout == 45


class TestMCPToolOutput:
    """Output model shape."""

    def test_dump_contains_all_fields(self) -> None:
        integration_id = str(uuid4())
        output = MCPToolOutput(tool_name="echo", integration_id=integration_id, result="hi", is_error=False)
        assert output.dump() == {
            "tool_name": "echo",
            "integration_id": integration_id,
            "result": "hi",
            "is_error": False,
        }

    def test_dump_applies_output_mapping(self) -> None:
        output = MCPToolOutput(tool_name="echo", integration_id=str(uuid4()), result={"n": 1}, is_error=False)
        assert output.dump({"answer": "${result.result}"}) == {"answer": {"n": 1}}

    def test_activity_name_is_registered(self) -> None:
        assert ActivityName.MCP_TOOL.value == "execute_mcp_tool_activity"
