"""Tests for manual_trigger activity."""

from typing import Any

import pytest

from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger


class TestManualTriggerPassThrough:
    """Manual trigger passes through user inputs."""

    @pytest.mark.asyncio
    async def test_inputs_included_in_output(self) -> None:
        inputs: dict[str, Any] = {"user_name": "alice", "action": "deploy"}
        result = await manual_trigger(inputs, None)
        assert result["output"]["user_name"] == "alice"
        assert result["output"]["action"] == "deploy"

    @pytest.mark.asyncio
    async def test_empty_inputs(self) -> None:
        result = await manual_trigger({}, None)
        assert result["output"] == {}

    @pytest.mark.asyncio
    async def test_no_control_in_result(self) -> None:
        result = await manual_trigger({"x": 1}, None)
        assert "control" not in result


class TestManualTriggerOutputMapping:
    """Output mapping integration for manual_trigger."""

    @pytest.mark.asyncio
    async def test_none_output_config_returns_full_result(self) -> None:
        result = await manual_trigger({"key": "val"}, None)
        assert result["output"]["key"] == "val"

    @pytest.mark.asyncio
    async def test_empty_output_config_suppresses_fields(self) -> None:
        result = await manual_trigger({"key": "val"}, {})
        assert result["output"] == {}

    @pytest.mark.asyncio
    async def test_field_mapping_extracts_specific_field(self) -> None:
        result = await manual_trigger(
            {"name": "bob", "age": 30},
            {"extracted_name": "${result.name}"},
        )
        assert result["output"]["extracted_name"] == "bob"
        assert "name" not in result["output"]
        assert "age" not in result["output"]


class TestManualTriggerStatusOverride:
    """Input containing 'status' key is treated as user data."""

    @pytest.mark.asyncio
    async def test_status_key_in_input_passes_through(self) -> None:
        result = await manual_trigger({"status": "custom"}, None)
        assert result["output"]["status"] == "custom"

    @pytest.mark.asyncio
    async def test_status_key_with_empty_mapping_suppressed(self) -> None:
        result = await manual_trigger({"status": "override"}, {})
        assert result["output"] == {}


class TestManualTriggerFailure:
    """Trigger failure produces ApplicationError (no output in result)."""

    @pytest.mark.asyncio
    async def test_bad_output_mapping_raises_application_error(self) -> None:
        from temporalio.exceptions import ApplicationError

        with pytest.raises(ApplicationError) as exc_info:
            await manual_trigger({"key": "val"}, {"x": "${result.nonexistent}"})
        assert exc_info.value.type == "OutputMappingError"


class TestManualTriggerNestedInput:
    """Nested input values are passed through correctly."""

    @pytest.mark.asyncio
    async def test_nested_dict_in_input(self) -> None:
        inputs: dict[str, Any] = {"foo": {"key": "value", "nested": {"deep": True}}}
        result = await manual_trigger(inputs, None)
        assert result["output"]["foo"] == {"key": "value", "nested": {"deep": True}}

    @pytest.mark.asyncio
    async def test_list_in_input(self) -> None:
        inputs: dict[str, Any] = {"items": [1, 2, 3]}
        result = await manual_trigger(inputs, None)
        assert result["output"]["items"] == [1, 2, 3]
