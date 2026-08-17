"""Tests for loop activity (for_each and do_while)."""

from typing import Any

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.loop import loop

# ---------------------------------------------------------------------------
# for_each loop
# ---------------------------------------------------------------------------


class TestForEachIteration:
    """for_each loop: iterating through items."""

    @pytest.mark.asyncio
    async def test_first_item_returns_iterate(self) -> None:
        config: dict[str, Any] = {"type": "for_each", "items": ["a", "b", "c"], "current_index": 0}
        result = await loop(config, None, {})
        assert result["control"]["next_port"] == "iterate"
        assert result["control"]["current_item"] == "a"
        assert result["control"]["next_index"] == 1

    @pytest.mark.asyncio
    async def test_middle_item_returns_iterate(self) -> None:
        config: dict[str, Any] = {"type": "for_each", "items": ["a", "b", "c"], "current_index": 1}
        result = await loop(config, None, {})
        assert result["control"]["next_port"] == "iterate"
        assert result["control"]["current_item"] == "b"
        assert result["control"]["next_index"] == 2

    @pytest.mark.asyncio
    async def test_iteration_count_in_output(self) -> None:
        config: dict[str, Any] = {"type": "for_each", "items": ["a", "b"], "current_index": 1}
        result = await loop(config, None, {})
        assert result["output"]["iteration_count"] == 1


class TestForEachCompletion:
    """for_each loop: all items processed."""

    @pytest.mark.asyncio
    async def test_past_last_item_returns_complete(self) -> None:
        config: dict[str, Any] = {"type": "for_each", "items": ["a", "b"], "current_index": 2}
        iteration_results: dict[str, list[Any]] = {"results": [1, 2]}
        result = await loop(config, None, iteration_results)
        assert result["control"]["next_port"] == "complete"
        assert result["control"]["current_item"] is None
        assert result["control"]["next_index"] == 2

    @pytest.mark.asyncio
    async def test_complete_includes_iteration_results(self) -> None:
        config: dict[str, Any] = {"type": "for_each", "items": ["a"], "current_index": 1}
        iteration_results: dict[str, list[Any]] = {"collected": [10]}
        result = await loop(config, None, iteration_results)
        assert result["output"]["iteration_results"] == iteration_results

    @pytest.mark.asyncio
    async def test_iterate_does_not_include_iteration_results(self) -> None:
        config: dict[str, Any] = {"type": "for_each", "items": ["a", "b"], "current_index": 0}
        result = await loop(config, None, {"collected": [10]})
        assert result["output"]["iteration_results"] is None


class TestForEachEmptyItems:
    """for_each loop: empty items list."""

    @pytest.mark.asyncio
    async def test_empty_items_returns_complete_immediately(self) -> None:
        config: dict[str, Any] = {"type": "for_each", "items": [], "current_index": 0}
        result = await loop(config, None, {})
        assert result["control"]["next_port"] == "complete"
        assert result["control"]["current_item"] is None


# ---------------------------------------------------------------------------
# do_while loop
# ---------------------------------------------------------------------------


class TestDoWhileFirstIteration:
    """do_while loop: first iteration always executes."""

    @pytest.mark.asyncio
    async def test_first_iteration_always_iterates(self) -> None:
        config: dict[str, Any] = {"type": "do_while", "current_index": 0, "condition_result": None}
        result = await loop(config, None, {})
        assert result["control"]["next_port"] == "iterate"
        assert result["control"]["next_index"] == 1

    @pytest.mark.asyncio
    async def test_first_iteration_with_false_condition_still_iterates(self) -> None:
        config: dict[str, Any] = {"type": "do_while", "current_index": 0, "condition_result": False}
        result = await loop(config, None, {})
        assert result["control"]["next_port"] == "iterate"


class TestDoWhileConditionTrue:
    """do_while loop: condition is true, continue iterating."""

    @pytest.mark.asyncio
    async def test_condition_true_continues(self) -> None:
        config: dict[str, Any] = {
            "type": "do_while",
            "current_index": 1,
            "condition_result": True,
        }
        result = await loop(config, None, {})
        assert result["control"]["next_port"] == "iterate"
        assert result["control"]["next_index"] == 2


class TestDoWhileConditionFalse:
    """do_while loop: condition is false, complete."""

    @pytest.mark.asyncio
    async def test_condition_false_completes(self) -> None:
        config: dict[str, Any] = {
            "type": "do_while",
            "current_index": 1,
            "condition_result": False,
        }
        iteration_results: dict[str, list[Any]] = {"collected": [1]}
        result = await loop(config, None, iteration_results)
        assert result["control"]["next_port"] == "complete"
        assert result["output"]["iteration_results"] == iteration_results


# ---------------------------------------------------------------------------
# Output mapping and control data
# ---------------------------------------------------------------------------


class TestLoopOutputMapping:
    """Output mapping integration for loop."""

    @pytest.mark.asyncio
    async def test_empty_output_config_suppresses_fields(self) -> None:
        config: dict[str, Any] = {"type": "for_each", "items": ["a"], "current_index": 0}
        result = await loop(config, {}, {})
        assert result["output"] == {}

    @pytest.mark.asyncio
    async def test_field_mapping_extracts_count(self) -> None:
        config: dict[str, Any] = {"type": "for_each", "items": ["a", "b"], "current_index": 1}
        result = await loop(config, {"count": "${result.iteration_count}"}, {})
        assert result["output"]["count"] == 1


class TestLoopControlData:
    """Control data contains next_port and next_index."""

    @pytest.mark.asyncio
    async def test_for_each_control_has_items_and_current_item(self) -> None:
        config: dict[str, Any] = {"type": "for_each", "items": ["x", "y"], "current_index": 0}
        result = await loop(config, None, {})
        ctrl = result["control"]
        assert ctrl["items"] == ["x", "y"]
        assert ctrl["current_item"] == "x"
        assert ctrl["current_index"] == 0

    @pytest.mark.asyncio
    async def test_do_while_control_has_current_index(self) -> None:
        config: dict[str, Any] = {
            "type": "do_while",
            "current_index": 2,
            "condition_result": True,
        }
        result = await loop(config, None, {})
        ctrl = result["control"]
        assert ctrl["current_index"] == 2
        assert ctrl["next_index"] == 3


# ---------------------------------------------------------------------------
# Unknown loop type and config defaults
# ---------------------------------------------------------------------------


class TestUnknownLoopType:
    """Unknown loop type raises ApplicationError."""

    @pytest.mark.asyncio
    async def test_unknown_type_raises(self) -> None:
        config: dict[str, Any] = {"type": "while_true", "current_index": 0}
        with pytest.raises(ApplicationError) as exc_info:
            await loop(config, None, {})
        assert "while_true" in str(exc_info.value)
        assert exc_info.value.type == "ConfigError"


class TestLoopConfigDefaults:
    """Missing config keys fall back to defaults."""

    @pytest.mark.asyncio
    async def test_missing_type_defaults_to_for_each(self) -> None:
        config: dict[str, Any] = {"items": ["a"], "current_index": 0}
        result = await loop(config, None, {})
        assert result["control"]["next_port"] == "iterate"
        assert result["control"]["current_item"] == "a"

    @pytest.mark.asyncio
    async def test_missing_items_defaults_to_empty_list(self) -> None:
        config: dict[str, Any] = {"type": "for_each", "current_index": 0}
        result = await loop(config, None, {})
        assert result["control"]["next_port"] == "complete"

    @pytest.mark.asyncio
    async def test_missing_current_index_defaults_to_zero(self) -> None:
        config: dict[str, Any] = {"type": "for_each", "items": ["x"]}
        result = await loop(config, None, {})
        assert result["control"]["current_item"] == "x"
        assert result["control"]["next_index"] == 1


class TestDoWhileIterationResults:
    """do_while iteration results behavior mirrors for_each."""

    @pytest.mark.asyncio
    async def test_do_while_iterate_does_not_include_iteration_results(self) -> None:
        config: dict[str, Any] = {
            "type": "do_while",
            "current_index": 0,
            "condition_result": None,
        }
        result = await loop(config, None, {"data": [1, 2]})
        assert result["output"]["iteration_results"] is None

    @pytest.mark.asyncio
    async def test_do_while_complete_includes_iteration_results(self) -> None:
        config: dict[str, Any] = {
            "type": "do_while",
            "current_index": 2,
            "condition_result": False,
        }
        iteration_results: dict[str, list[Any]] = {"collected": [1, 2]}
        result = await loop(config, None, iteration_results)
        assert result["output"]["iteration_results"] == iteration_results

    @pytest.mark.asyncio
    async def test_do_while_iteration_count_in_output(self) -> None:
        config: dict[str, Any] = {
            "type": "do_while",
            "current_index": 3,
            "condition_result": True,
        }
        result = await loop(config, None, {})
        assert result["output"]["iteration_count"] == 3


class TestDoWhileOutputMapping:
    """Output mapping for do_while loop."""

    @pytest.mark.asyncio
    async def test_do_while_empty_output_config_suppresses(self) -> None:
        config: dict[str, Any] = {
            "type": "do_while",
            "current_index": 0,
            "condition_result": None,
        }
        result = await loop(config, {}, {})
        assert result["output"] == {}

    @pytest.mark.asyncio
    async def test_do_while_output_mapping_does_not_affect_control(self) -> None:
        config: dict[str, Any] = {
            "type": "do_while",
            "current_index": 0,
            "condition_result": None,
        }
        result = await loop(config, {}, {})
        assert result["control"]["next_port"] == "iterate"
