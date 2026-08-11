"""Tests for converge activity."""

from typing import Any

import pytest

from syntara.workflows.workflow_engine.activities.converge import converge


class TestConvergeMergeResults:
    """Merging results from multiple predecessors."""

    @pytest.mark.asyncio
    async def test_two_predecessors_merged(self) -> None:
        predecessors: dict[str, dict[str, Any]] = {
            "node_a": {"value": 1},
            "node_b": {"value": 2},
        }
        result = await converge({}, None, predecessors)
        assert result["output"]["branch_count"] == 2
        assert result["output"]["completed_count"] == 2
        assert set(result["output"]["completed_branch_node_ids"]) == {"node_a", "node_b"}

    @pytest.mark.asyncio
    async def test_single_predecessor(self) -> None:
        predecessors: dict[str, dict[str, Any]] = {"only_node": {"x": 10}}
        result = await converge({}, None, predecessors)
        assert result["output"]["branch_count"] == 1
        assert result["output"]["completed_branch_node_ids"] == ["only_node"]


class TestConvergeEmptyPredecessors:
    """Empty predecessor results."""

    @pytest.mark.asyncio
    async def test_empty_predecessors(self) -> None:
        result = await converge({}, None, {})
        assert result["output"]["branch_count"] == 0
        assert result["output"]["completed_count"] == 0
        assert result["output"]["completed_branch_node_ids"] == []


class TestConvergeOutputMapping:
    """Output mapping integration."""

    @pytest.mark.asyncio
    async def test_none_output_config_returns_full_result(self) -> None:
        result = await converge({}, None, {"a": {"v": 1}})
        assert "branch_count" in result["output"]
        assert "completed_branch_node_ids" in result["output"]

    @pytest.mark.asyncio
    async def test_empty_output_config_suppresses_fields(self) -> None:
        result = await converge({}, {}, {"a": {"v": 1}})
        assert result["output"] == {}

    @pytest.mark.asyncio
    async def test_field_mapping_extracts_count(self) -> None:
        result = await converge(
            {},
            {"count": "${result.branch_count}"},
            {"a": {}, "b": {}},
        )
        assert result["output"]["count"] == 2
        assert "branch_count" not in result["output"]

    @pytest.mark.asyncio
    async def test_no_control_in_result(self) -> None:
        result = await converge({}, None, {})
        assert "control" not in result


class TestConvergeManyPredecessors:
    """Converge handles many predecessors correctly."""

    @pytest.mark.asyncio
    async def test_five_predecessors_counted(self) -> None:
        predecessors = {f"node_{i}": {"val": i} for i in range(5)}
        result = await converge({}, None, predecessors)
        assert result["output"]["branch_count"] == 5
        assert result["output"]["completed_count"] == 5
        assert len(result["output"]["completed_branch_node_ids"]) == 5


class TestConvergePredecessorValuesNotLeaked:
    """Predecessor result values are not included in converge output."""

    @pytest.mark.asyncio
    async def test_predecessor_values_not_in_output(self) -> None:
        predecessors = {"node_a": {"secret": "data"}}
        result = await converge({}, None, predecessors)
        assert "secret" not in result["output"]
        assert "node_a" not in result["output"]

    @pytest.mark.asyncio
    async def test_input_config_strategy_all_default(self) -> None:
        result = await converge({}, None, {"a": {}})
        assert result["output"]["branch_count"] == 1


class TestConvergeAnyStrategy:
    """Tests for 'any' convergence strategy."""

    @pytest.mark.asyncio
    async def test_any_two_of_three_completed(self) -> None:
        predecessors: dict[str, dict[str, Any]] = {
            "node_a": {"value": 1},
            "node_b": {"value": 2},
        }
        config = {"strategy": "any", "n_required": 2, "total_branches": 3}
        result = await converge(config, None, predecessors)
        assert result["output"]["branch_count"] == 3
        assert result["output"]["completed_count"] == 2
        assert set(result["output"]["completed_branch_node_ids"]) == {"node_a", "node_b"}

    @pytest.mark.asyncio
    async def test_any_one_of_five(self) -> None:
        config = {"strategy": "any", "n_required": 1, "total_branches": 5}
        result = await converge(config, None, {"fast_node": {"done": True}})
        assert result["output"]["branch_count"] == 5
        assert result["output"]["completed_count"] == 1
        assert result["output"]["completed_branch_node_ids"] == ["fast_node"]

    @pytest.mark.asyncio
    async def test_any_all_completed(self) -> None:
        predecessors = {f"node_{i}": {"val": i} for i in range(3)}
        config = {"strategy": "any", "n_required": 2, "total_branches": 3}
        result = await converge(config, None, predecessors)
        assert result["output"]["branch_count"] == 3
        assert result["output"]["completed_count"] == 3

    @pytest.mark.asyncio
    async def test_any_with_output_mapping(self) -> None:
        config = {"strategy": "any", "n_required": 1, "total_branches": 3}
        result = await converge(
            config,
            {"done": "${result.completed_count}"},
            {"a": {}},
        )
        assert result["output"]["done"] == 1
        assert "branch_count" not in result["output"]

    @pytest.mark.asyncio
    async def test_total_branches_from_config(self) -> None:
        config = {"total_branches": 10}
        result = await converge(config, None, {"a": {}, "b": {}})
        assert result["output"]["branch_count"] == 10
        assert result["output"]["completed_count"] == 2

    @pytest.mark.asyncio
    async def test_total_branches_defaults_to_completed(self) -> None:
        result = await converge({}, None, {"a": {}, "b": {}})
        assert result["output"]["branch_count"] == 2
        assert result["output"]["completed_count"] == 2

    @pytest.mark.asyncio
    async def test_any_n_required_equals_total(self) -> None:
        predecessors = {f"n{i}": {"v": i} for i in range(3)}
        config = {"strategy": "any", "n_required": 3, "total_branches": 3}
        result = await converge(config, None, predecessors)
        assert result["output"]["branch_count"] == 3
        assert result["output"]["completed_count"] == 3

    @pytest.mark.asyncio
    async def test_any_zero_completed(self) -> None:
        config = {"strategy": "any", "n_required": 1, "total_branches": 3}
        result = await converge(config, None, {})
        assert result["output"]["branch_count"] == 3
        assert result["output"]["completed_count"] == 0
        assert result["output"]["completed_branch_node_ids"] == []

    @pytest.mark.asyncio
    async def test_any_n_required_exceeds_total_branches(self) -> None:
        config = {"strategy": "any", "n_required": 5, "total_branches": 3}
        result = await converge(config, None, {"a": {}, "b": {}})
        assert result["output"]["branch_count"] == 3
        assert result["output"]["completed_count"] == 2

    @pytest.mark.asyncio
    async def test_strategy_any_without_n_required(self) -> None:
        config = {"strategy": "any", "total_branches": 3}
        result = await converge(config, None, {"a": {}})
        assert result["output"]["completed_count"] == 1
