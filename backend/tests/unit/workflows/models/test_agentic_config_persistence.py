"""Tests for agentic node configuration persistence (AAP-66976).

Verifies that tool_selection_strategy, tool_selections, response_schema,
and integration_connections survive round-trip through:
- Pydantic model_validate → model_dump (serialization)
- JSONB-equivalent dict → model → dict (workflow save/load)
- Alias handling (response_schema ↔ responseSchema)
- Edge cases (empty, None, complex schemas)
"""

import json

import pytest
from pydantic import ValidationError

from syntara.workflows.workflow_engine.models.workflow_definition import AgenticExecutorParameters

VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"
VALID_UUID_2 = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"


class TestToolSelectionStrategyPersistence:
    """Verify tool_selection_strategy and tool_selections survive save/load."""

    def test_selected_strategy_with_tools_round_trip(self) -> None:
        """SELECTED + tool UUIDs persist through model_validate → model_dump."""
        input_dict = {
            "prompt": "Analyze data",
            "tool_selection_strategy": "SELECTED",
            "tool_selections": [VALID_UUID, VALID_UUID_2],
        }
        config = AgenticExecutorParameters.model_validate(input_dict)
        output_dict = config.model_dump()

        assert output_dict["tool_selection_strategy"] == "SELECTED"
        assert output_dict["tool_selections"] == [VALID_UUID, VALID_UUID_2]

    def test_all_strategy_round_trip(self) -> None:
        input_dict = {"prompt": "test", "tool_selection_strategy": "ALL"}
        config = AgenticExecutorParameters.model_validate(input_dict)
        output_dict = config.model_dump()

        assert output_dict["tool_selection_strategy"] == "ALL"
        assert output_dict["tool_selections"] == []

    def test_none_strategy_round_trip(self) -> None:
        input_dict = {"prompt": "test", "tool_selection_strategy": "NONE"}
        config = AgenticExecutorParameters.model_validate(input_dict)
        output_dict = config.model_dump()

        assert output_dict["tool_selection_strategy"] == "NONE"
        assert output_dict["tool_selections"] == []

    def test_no_strategy_defaults_round_trip(self) -> None:
        """Omitting tool_selection_strategy defaults to None."""
        input_dict = {"prompt": "test"}
        config = AgenticExecutorParameters.model_validate(input_dict)
        output_dict = config.model_dump()

        assert output_dict["tool_selection_strategy"] is None
        assert output_dict["tool_selections"] == []

    def test_jsonb_simulation_round_trip(self) -> None:
        """Simulate JSONB: dict → JSON string → dict → model_validate."""
        original = {
            "prompt": "test",
            "tool_selection_strategy": "SELECTED",
            "tool_selections": [VALID_UUID],
        }
        json_str = json.dumps(original)
        loaded = json.loads(json_str)
        config = AgenticExecutorParameters.model_validate(loaded)

        assert config.tool_selection_strategy == "SELECTED"
        assert config.tool_selections == [VALID_UUID]


class TestResponseSchemaPersistence:
    """Verify response_schema survives save/load with alias handling."""

    def test_response_schema_snake_case_round_trip(self) -> None:
        schema = {"type": "object", "properties": {"summary": {"type": "string"}}}
        input_dict = {"prompt": "test", "response_schema": schema}
        config = AgenticExecutorParameters.model_validate(input_dict)
        output_dict = config.model_dump()

        assert output_dict["response_schema"] == schema

    def test_response_schema_camel_case_alias_round_trip(self) -> None:
        """ResponseSchema (camelCase) accepted and persists as response_schema."""
        schema = {"type": "object", "properties": {"score": {"type": "number"}}}
        input_dict = {"prompt": "test", "responseSchema": schema}
        config = AgenticExecutorParameters.model_validate(input_dict)
        output_dict = config.model_dump()

        assert output_dict["response_schema"] == schema

    def test_response_schema_by_alias_serialization(self) -> None:
        """by_alias=True serializes to responseSchema for API responses."""
        schema = {"type": "string"}
        config = AgenticExecutorParameters(prompt="test", responseSchema=schema)
        output_dict = config.model_dump(by_alias=True)

        assert "responseSchema" in output_dict
        assert output_dict["responseSchema"] == schema

    def test_complex_nested_schema_preserved(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "servers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "hostname": {"type": "string"},
                            "status": {"type": "string", "enum": ["up", "down"]},
                        },
                        "required": ["hostname"],
                    },
                },
            },
            "required": ["servers"],
        }
        config = AgenticExecutorParameters.model_validate({"prompt": "test", "responseSchema": schema})
        output = config.model_dump()

        assert output["response_schema"] == schema
        assert output["response_schema"]["properties"]["servers"]["items"]["required"] == ["hostname"]

    def test_none_response_schema_round_trip(self) -> None:
        config = AgenticExecutorParameters.model_validate({"prompt": "test"})
        output = config.model_dump()

        assert output["response_schema"] is None

    def test_response_schema_jsonb_simulation(self) -> None:
        """Simulate full JSONB round-trip including JSON serialization."""
        schema = {"type": "object", "properties": {"result": {"type": "boolean"}}}
        original = {"prompt": "test", "response_schema": schema}

        json_str = json.dumps(original)
        loaded = json.loads(json_str)
        config = AgenticExecutorParameters.model_validate(loaded)
        output = config.model_dump()

        assert output["response_schema"] == schema


class TestIntegrationConnectionsPersistence:
    """Verify integration_connections survive save/load."""

    def test_integration_connections_round_trip(self) -> None:
        connections = [
            {"integration_id": VALID_UUID, "credential_id": VALID_UUID_2},
        ]
        config = AgenticExecutorParameters.model_validate(
            {
                "prompt": "test",
                "integration_connections": connections,
            }
        )
        output = config.model_dump()

        assert len(output["integration_connections"]) == 1
        assert output["integration_connections"][0]["integration_id"] == VALID_UUID
        assert output["integration_connections"][0]["credential_id"] == VALID_UUID_2

    def test_multiple_connections_preserved(self) -> None:
        connections = [
            {"integration_id": VALID_UUID, "credential_id": VALID_UUID_2},
            {"integration_id": VALID_UUID_2, "credential_id": VALID_UUID},
        ]
        config = AgenticExecutorParameters.model_validate(
            {
                "prompt": "test",
                "integration_connections": connections,
            }
        )
        output = config.model_dump()

        assert len(output["integration_connections"]) == 2

    def test_none_connections_round_trip(self) -> None:
        config = AgenticExecutorParameters.model_validate({"prompt": "test"})
        output = config.model_dump()

        assert output["integration_connections"] is None

    def test_connections_jsonb_simulation(self) -> None:
        connections = [{"integration_id": VALID_UUID, "credential_id": VALID_UUID_2}]
        original = {"prompt": "test", "integration_connections": connections}

        json_str = json.dumps(original)
        loaded = json.loads(json_str)
        config = AgenticExecutorParameters.model_validate(loaded)
        output = config.model_dump()

        assert output["integration_connections"][0]["integration_id"] == VALID_UUID


class TestFullConfigPersistence:
    """Verify all fields together survive save/load."""

    def test_complete_agentic_config_round_trip(self) -> None:
        """All fields set — verify nothing is lost."""
        input_dict = {
            "prompt": "Analyze the incident and classify severity",
            "agent": "incident-triage",
            "llm_model_id": VALID_UUID_2,
            "credential_id": VALID_UUID,
            "tool_selection_strategy": "SELECTED",
            "tool_selections": [VALID_UUID_2],
            "responseSchema": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                    "summary": {"type": "string"},
                },
                "required": ["severity", "summary"],
            },
            "integration_connections": [
                {"integration_id": VALID_UUID, "credential_id": VALID_UUID_2},
            ],
            "file_ids": [VALID_UUID],
        }

        config = AgenticExecutorParameters.model_validate(input_dict)
        output = config.model_dump()

        assert output["prompt"] == "Analyze the incident and classify severity"
        assert output["agent"] == "incident-triage"
        assert output["llm_model_id"] == VALID_UUID_2
        assert output["credential_id"] == VALID_UUID
        assert output["tool_selection_strategy"] == "SELECTED"
        assert output["tool_selections"] == [VALID_UUID_2]
        assert output["response_schema"]["type"] == "object"
        assert output["response_schema"]["required"] == ["severity", "summary"]
        assert len(output["integration_connections"]) == 1
        assert output["file_ids"] == [VALID_UUID]

    def test_complete_config_jsonb_simulation(self) -> None:
        """Full config survives JSON serialize → deserialize → validate."""
        input_dict = {
            "prompt": "test",
            "tool_selection_strategy": "ALL",
            "tool_selections": [],
            "response_schema": {"type": "string"},
            "integration_connections": [
                {"integration_id": VALID_UUID, "credential_id": VALID_UUID_2},
            ],
        }

        json_str = json.dumps(input_dict)
        loaded = json.loads(json_str)
        config = AgenticExecutorParameters.model_validate(loaded)
        output = config.model_dump()

        assert output["tool_selection_strategy"] == "ALL"
        assert output["tool_selections"] == []
        assert output["response_schema"] == {"type": "string"}
        assert len(output["integration_connections"]) == 1

    def test_minimal_config_round_trip(self) -> None:
        """Only required fields — optional fields default correctly."""
        config = AgenticExecutorParameters.model_validate({"prompt": "test"})
        output = config.model_dump()

        assert output["prompt"] == "test"
        assert output["tool_selection_strategy"] is None
        assert output["tool_selections"] == []
        assert output["response_schema"] is None
        assert output["integration_connections"] is None
        assert output["credential_id"] is None
        assert output["file_ids"] == []

    def test_re_validate_after_dump_produces_same_output(self) -> None:
        """model_dump → model_validate → model_dump is idempotent."""
        input_dict = {
            "prompt": "test",
            "tool_selection_strategy": "SELECTED",
            "tool_selections": [VALID_UUID],
            "response_schema": {"type": "object", "properties": {"x": {"type": "integer"}}},
        }

        config1 = AgenticExecutorParameters.model_validate(input_dict)
        dump1 = config1.model_dump()
        config2 = AgenticExecutorParameters.model_validate(dump1)
        dump2 = config2.model_dump()

        assert dump1 == dump2


class TestPersistenceEdgeCases:
    """Edge cases that could break persistence."""

    def test_template_expression_in_strategy_persists(self) -> None:
        """Template expressions should survive round-trip without validation."""
        config = AgenticExecutorParameters.model_validate(
            {
                "prompt": "test",
                "tool_selection_strategy": "${input.strategy}",
            }
        )
        output = config.model_dump()
        assert output["tool_selection_strategy"] == "${input.strategy}"

    def test_template_expression_in_tool_selections_persists(self) -> None:
        config = AgenticExecutorParameters.model_validate(
            {
                "prompt": "test",
                "tool_selection_strategy": "SELECTED",
                "tool_selections": ["${input.tools}"],
            }
        )
        output = config.model_dump()
        assert output["tool_selections"] == ["${input.tools}"]

    def test_template_expression_in_response_schema_persists(self) -> None:
        config = AgenticExecutorParameters.model_validate(
            {
                "prompt": "test",
                "responseSchema": "${input.schema}",
            }
        )
        output = config.model_dump()
        assert output["response_schema"] == "${input.schema}"

    def test_invalid_tool_uuid_rejected_not_silently_stored(self) -> None:
        """Invalid tool_selections UUIDs must be rejected, not silently persisted."""
        with pytest.raises(ValidationError):
            AgenticExecutorParameters.model_validate(
                {
                    "prompt": "test",
                    "tool_selection_strategy": "SELECTED",
                    "tool_selections": ["not-a-uuid"],
                }
            )


class TestInvocationMetadataPersistence:
    """Verify InvocationMetadata fields survive round-trip (invocation path).

    Mirrors AgenticExecutorParameters tests to ensure both validation
    paths handle persistence identically (Aaron review feedback).
    """

    def test_tool_selection_round_trip(self) -> None:
        """Tool selection fields persist through model_validate → model_dump."""
        from syntara.agent_orchestrator.models.context_data import InvocationMetadata

        input_dict = {
            "tool_selection_strategy": "SELECTED",
            "tool_selections": [VALID_UUID, VALID_UUID_2],
        }
        meta = InvocationMetadata.model_validate(input_dict)
        output = meta.model_dump()

        assert output["tool_selection_strategy"] == "SELECTED"
        assert output["tool_selections"] == [VALID_UUID, VALID_UUID_2]

    def test_response_schema_round_trip(self) -> None:
        """Response schema persists through OpaqueResponseSchema wrapping."""
        from syntara.agent_orchestrator.models.context_data import InvocationMetadata

        schema = {"type": "object", "properties": {"result": {"type": "string"}}}
        meta = InvocationMetadata.model_validate({"response_schema": schema})
        output = meta.model_dump()

        assert output["response_schema"] == schema

    def test_integration_connections_round_trip(self) -> None:
        from syntara.agent_orchestrator.models.context_data import InvocationMetadata

        connections = [{"integration_id": VALID_UUID, "credential_id": VALID_UUID_2}]
        meta = InvocationMetadata.model_validate({"integration_connections": connections})
        output = meta.model_dump()

        assert len(output["integration_connections"]) == 1
        assert output["integration_connections"][0]["integration_id"] == VALID_UUID

    def test_all_fields_combined_round_trip(self) -> None:
        from syntara.agent_orchestrator.models.context_data import InvocationMetadata

        input_dict = {
            "tool_selection_strategy": "ALL",
            "tool_selections": [],
            "response_schema": {"type": "string"},
            "integration_connections": [
                {"integration_id": VALID_UUID, "credential_id": VALID_UUID_2},
            ],
        }
        meta = InvocationMetadata.model_validate(input_dict)
        output = meta.model_dump()

        assert output["tool_selection_strategy"] == "ALL"
        assert output["tool_selections"] == []
        assert output["response_schema"] == {"type": "string"}
        assert len(output["integration_connections"]) == 1

    def test_defaults_round_trip(self) -> None:
        """Omitted fields default correctly."""
        from syntara.agent_orchestrator.models.context_data import InvocationMetadata

        meta = InvocationMetadata.model_validate({})
        output = meta.model_dump()

        assert output["tool_selection_strategy"] is None
        assert output["tool_selections"] == []
        assert output["response_schema"] is None
        assert output["integration_connections"] is None

    def test_jsonb_simulation_round_trip(self) -> None:
        """Simulate JSONB persistence for invocation context_data."""
        from syntara.agent_orchestrator.models.context_data import InvocationMetadata

        original = {
            "tool_selection_strategy": "SELECTED",
            "tool_selections": [VALID_UUID],
            "response_schema": {"type": "object", "properties": {"x": {"type": "integer"}}},
        }
        json_str = json.dumps(original)
        loaded = json.loads(json_str)
        meta = InvocationMetadata.model_validate(loaded)

        assert meta.tool_selection_strategy == "SELECTED"
        assert meta.tool_selections == [VALID_UUID]
        assert meta.response_schema is not None
