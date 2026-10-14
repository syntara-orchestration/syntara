"""Tests for subworkflow_trigger activity, type/activity enums, and registration."""

from typing import Any

import pytest

from syntara.workflows.workflow_engine.activities.registry import ACTIVITY_REGISTRY
from syntara.workflows.workflow_engine.activities.subworkflow_trigger import subworkflow_trigger
from syntara.workflows.workflow_engine.dynamic_workflow import ALLOWED_TRIGGER_TYPES
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, NodeType


class TestSubworkflowTriggerEnums:
    """The new child-side trigger type/activity enum members exist with matching values."""

    def test_activity_name_value(self) -> None:
        assert ActivityName.SUBWORKFLOW_TRIGGER == "subworkflow_trigger"

    def test_node_type_value(self) -> None:
        assert NodeType.SUBWORKFLOW_TRIGGER == "subworkflow_trigger"

    def test_node_type_matches_activity_name(self) -> None:
        # For triggers, the node type string must equal the activity name string
        # (dynamic dispatch uses node.type as the activity name).
        assert NodeType.SUBWORKFLOW_TRIGGER.value == ActivityName.SUBWORKFLOW_TRIGGER.value

    def test_type_is_recognized_as_trigger(self) -> None:
        # Trigger recognition everywhere uses the `_trigger` suffix convention.
        assert NodeType.SUBWORKFLOW_TRIGGER.value.endswith("_trigger")


class TestSubworkflowTriggerRegistration:
    """The activity is registered and allowed for dynamic dispatch."""

    def test_registered_in_activity_registry(self) -> None:
        assert ActivityName.SUBWORKFLOW_TRIGGER in ACTIVITY_REGISTRY
        assert ACTIVITY_REGISTRY[ActivityName.SUBWORKFLOW_TRIGGER] is subworkflow_trigger

    def test_in_allowed_trigger_types(self) -> None:
        assert ActivityName.SUBWORKFLOW_TRIGGER in ALLOWED_TRIGGER_TYPES


class TestSubworkflowTriggerPassThrough:
    """Subworkflow trigger passes through the inputs supplied at invocation."""

    @pytest.mark.asyncio
    async def test_inputs_included_in_output(self) -> None:
        inputs: dict[str, Any] = {"env": "prod", "replicas": 3}
        result = await subworkflow_trigger(inputs, None)
        assert result["output"]["env"] == "prod"
        assert result["output"]["replicas"] == 3

    @pytest.mark.asyncio
    async def test_empty_inputs(self) -> None:
        result = await subworkflow_trigger({}, None)
        assert result["output"] == {}

    @pytest.mark.asyncio
    async def test_no_control_in_result(self) -> None:
        result = await subworkflow_trigger({"x": 1}, None)
        assert "control" not in result


class TestSubworkflowTriggerOutputMapping:
    """Output mapping integration for subworkflow_trigger."""

    @pytest.mark.asyncio
    async def test_none_output_config_returns_full_result(self) -> None:
        result = await subworkflow_trigger({"key": "val"}, None)
        assert result["output"]["key"] == "val"

    @pytest.mark.asyncio
    async def test_empty_output_config_suppresses_fields(self) -> None:
        result = await subworkflow_trigger({"key": "val"}, {})
        assert result["output"] == {}

    @pytest.mark.asyncio
    async def test_field_mapping_extracts_specific_field(self) -> None:
        result = await subworkflow_trigger(
            {"name": "bob", "age": 30},
            {"extracted_name": "${result.name}"},
        )
        assert result["output"]["extracted_name"] == "bob"
        assert "name" not in result["output"]
        assert "age" not in result["output"]

    @pytest.mark.asyncio
    async def test_bad_output_mapping_raises_application_error(self) -> None:
        from temporalio.exceptions import ApplicationError

        with pytest.raises(ApplicationError) as exc_info:
            await subworkflow_trigger({"key": "val"}, {"x": "${result.nonexistent}"})
        assert exc_info.value.type == "OutputMappingError"


class TestSubworkflowTriggerNestedInput:
    """Nested input values are passed through correctly."""

    @pytest.mark.asyncio
    async def test_nested_dict_in_input(self) -> None:
        inputs: dict[str, Any] = {"foo": {"key": "value", "nested": {"deep": True}}}
        result = await subworkflow_trigger(inputs, None)
        assert result["output"]["foo"] == {"key": "value", "nested": {"deep": True}}

    @pytest.mark.asyncio
    async def test_list_in_input(self) -> None:
        inputs: dict[str, Any] = {"items": [1, 2, 3]}
        result = await subworkflow_trigger(inputs, None)
        assert result["output"]["items"] == [1, 2, 3]
