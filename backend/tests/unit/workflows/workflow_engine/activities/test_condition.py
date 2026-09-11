"""Tests for condition activity."""

import asyncio
import time
from typing import Any
from unittest.mock import patch

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.condition import condition


class TestConditionTrueEvaluation:
    """Condition evaluates to true."""

    @pytest.mark.asyncio
    async def test_true_literal_returns_true_port(self) -> None:
        result = await condition({"condition": "True", "namespace": {}}, None)
        assert result["control"]["next_port"] == "true"

    @pytest.mark.asyncio
    async def test_true_literal_output_status_completed(self) -> None:
        result = await condition({"condition": "True", "namespace": {}}, None)
        assert result["output"]["evaluated_result"] is True

    @pytest.mark.asyncio
    async def test_comparison_true(self) -> None:
        result = await condition({"condition": "5 > 3", "namespace": {}}, None)
        assert result["control"]["next_port"] == "true"
        assert result["output"]["evaluated_result"] is True


class TestConditionFalseEvaluation:
    """Condition evaluates to false."""

    @pytest.mark.asyncio
    async def test_false_literal_returns_false_port(self) -> None:
        result = await condition({"condition": "False", "namespace": {}}, None)
        assert result["control"]["next_port"] == "false"

    @pytest.mark.asyncio
    async def test_false_literal_output_status_completed(self) -> None:
        result = await condition({"condition": "False", "namespace": {}}, None)
        assert result["output"]["evaluated_result"] is False

    @pytest.mark.asyncio
    async def test_comparison_false(self) -> None:
        result = await condition({"condition": "3 > 5", "namespace": {}}, None)
        assert result["control"]["next_port"] == "false"
        assert result["output"]["evaluated_result"] is False


class TestConditionMissingConfig:
    """Missing condition expression raises ApplicationError."""

    @pytest.mark.asyncio
    async def test_empty_condition_raises(self) -> None:
        with pytest.raises(ApplicationError) as exc_info:
            await condition({"condition": "", "namespace": {}}, None)
        assert exc_info.value.type == "ConfigError"

    @pytest.mark.asyncio
    async def test_missing_condition_key_raises(self) -> None:
        with pytest.raises(ApplicationError) as exc_info:
            await condition({"namespace": {}}, None)
        assert "Missing 'condition'" in str(exc_info.value)


class TestConditionEvaluationFailure:
    """Condition evaluation raises ApplicationError."""

    @pytest.mark.asyncio
    async def test_invalid_expression_raises(self) -> None:
        with (
            patch(
                "syntara.workflows.workflow_engine.activities.condition.safe_eval_with_namespace",
                side_effect=ValueError("bad expression"),
            ),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await condition({"condition": "bad_expr", "namespace": {}}, None)
        assert exc_info.value.type == "ConditionEvaluationError"

    @pytest.mark.asyncio
    async def test_evaluation_error_is_non_retryable(self) -> None:
        with (
            patch(
                "syntara.workflows.workflow_engine.activities.condition.safe_eval_with_namespace",
                side_effect=ValueError("invalid expression"),
            ),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await condition({"condition": "x", "namespace": {}}, None)
        assert exc_info.value.non_retryable is True

    @pytest.mark.asyncio
    async def test_uncaught_exception_propagates(self) -> None:
        """Exceptions outside the explicit catch list should propagate to Temporal."""
        with (
            patch(
                "syntara.workflows.workflow_engine.activities.condition.safe_eval_with_namespace",
                side_effect=OSError("disk full"),
            ),
            pytest.raises(OSError, match="disk full"),
        ):
            await condition({"condition": "x", "namespace": {}}, None)


class TestConditionOutputMapping:
    """Output mapping integration."""

    @pytest.mark.asyncio
    async def test_none_output_config_returns_full_result(self) -> None:
        result = await condition({"condition": "True", "namespace": {}}, None)
        assert "evaluated_result" in result["output"]

    @pytest.mark.asyncio
    async def test_empty_output_config_suppresses_fields(self) -> None:
        result = await condition({"condition": "True", "namespace": {}}, {})
        assert result["output"] == {}

    @pytest.mark.asyncio
    async def test_field_mapping_extracts_specific_field(self) -> None:
        result = await condition(
            {"condition": "True", "namespace": {}},
            {"eval": "${result.evaluated_result}"},
        )
        assert result["output"]["eval"] is True
        assert "evaluated_result" not in result["output"]


class TestConditionControlData:
    """Control data contains correct next_port."""

    @pytest.mark.asyncio
    async def test_true_control_next_port(self) -> None:
        result = await condition({"condition": "True", "namespace": {}}, None)
        assert result["control"] == {"next_port": "true"}

    @pytest.mark.asyncio
    async def test_false_control_next_port(self) -> None:
        result = await condition({"condition": "False", "namespace": {}}, None)
        assert result["control"] == {"next_port": "false"}

    @pytest.mark.asyncio
    async def test_output_mapping_does_not_affect_control(self) -> None:
        result = await condition({"condition": "True", "namespace": {}}, {})
        assert result["control"] == {"next_port": "true"}


class TestConditionNoneValue:
    """Condition key present but value is None raises ApplicationError."""

    @pytest.mark.asyncio
    async def test_none_condition_value_raises(self) -> None:
        with pytest.raises(ApplicationError) as exc_info:
            await condition({"condition": None, "namespace": {}}, None)
        assert exc_info.value.type == "ConfigError"


class TestConditionErrorMessageContent:
    """Error messages contain useful diagnostic info."""

    @pytest.mark.asyncio
    async def test_evaluation_error_message_includes_expression(self) -> None:
        with (
            patch(
                "syntara.workflows.workflow_engine.activities.condition.safe_eval_with_namespace",
                side_effect=ValueError("syntax error"),
            ),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await condition({"condition": "x + y", "namespace": {}}, None)
        assert "x + y" in str(exc_info.value)
        assert "syntax error" in str(exc_info.value)


class TestConditionOutputMappingOnFailure:
    """Output mapping is skipped because failures now raise instead of return."""

    @pytest.mark.asyncio
    async def test_missing_config_raises_not_returns(self) -> None:
        with pytest.raises(ApplicationError):
            await condition({"namespace": {}}, {"eval": "${result.evaluated_result}"})

    @pytest.mark.asyncio
    async def test_eval_error_raises_not_returns(self) -> None:
        with (
            patch(
                "syntara.workflows.workflow_engine.activities.condition.safe_eval_with_namespace",
                side_effect=ValueError("bad"),
            ),
            pytest.raises(ApplicationError),
        ):
            await condition({"condition": "bad", "namespace": {}}, {"eval": "${result.evaluated_result}"})


class TestConditionWithNamespace:
    """Test condition evaluation with namespace variable lookup (Tier 2)."""

    @pytest.mark.asyncio
    async def test_variable_lookup_from_namespace(self) -> None:
        """Variable values are looked up from namespace."""
        namespace = {"status": "completed"}
        result = await condition({"condition": "${status} == 'completed'", "namespace": namespace}, None)
        assert result["control"]["next_port"] == "true"
        assert result["output"]["evaluated_result"] is True

    @pytest.mark.asyncio
    async def test_numeric_variable_type_preserved(self) -> None:
        """Numeric types are preserved (not converted to strings)."""
        namespace = {"count": 42}
        result = await condition({"condition": "${count} > 40", "namespace": namespace}, None)
        assert result["control"]["next_port"] == "true"
        assert result["output"]["evaluated_result"] is True

    @pytest.mark.asyncio
    async def test_nested_dict_access(self) -> None:
        """Dotted path access for nested dicts."""
        namespace = {"fetch_order": {"riskScore": 0.8}}
        result = await condition({"condition": "${fetch_order.riskScore} > 0.7", "namespace": namespace}, None)
        assert result["control"]["next_port"] == "true"
        assert result["output"]["evaluated_result"] is True

    @pytest.mark.asyncio
    async def test_complex_expression_with_namespace(self) -> None:
        """Complex boolean expressions with namespace variables."""
        namespace = {"age": 25, "verified": True}
        result = await condition({"condition": "${age} >= 18 and ${verified} == True", "namespace": namespace}, None)
        assert result["control"]["next_port"] == "true"
        assert result["output"]["evaluated_result"] is True

    @pytest.mark.asyncio
    async def test_namespace_is_defensive_copy(self) -> None:
        """Namespace is copied defensively to prevent mutations."""
        namespace = {"value": 10}
        result = await condition({"condition": "${value} == 10", "namespace": namespace}, None)
        # Verify original namespace unchanged (defensive copy worked)
        assert namespace == {"value": 10}
        assert result["control"]["next_port"] == "true"

    @pytest.mark.asyncio
    async def test_variable_not_found_in_namespace(self) -> None:
        """Missing variable in namespace raises ApplicationError."""
        namespace = {"status": "ok"}
        with pytest.raises(ApplicationError) as exc_info:
            await condition({"condition": "${unknown} == 'value'", "namespace": namespace}, None)
        assert exc_info.value.type == "ConditionEvaluationError"
        assert "unknown" in str(exc_info.value)


class TestConditionVisualBuilderOperators:
    """Word operators from the visual builder must evaluate (AAP-91413)."""

    @pytest.mark.asyncio
    async def test_exists_true_routes_true_port(self) -> None:
        result = await condition(
            {"condition": "${node.status} exists", "namespace": {"node": {"status": "ok"}}},
            None,
        )
        assert result["control"]["next_port"] == "true"
        assert result["output"]["evaluated_result"] is True

    @pytest.mark.asyncio
    async def test_exists_false_when_path_missing(self) -> None:
        result = await condition(
            {"condition": "${node.status} exists", "namespace": {"node": {}}},
            None,
        )
        assert result["control"]["next_port"] == "false"
        assert result["output"]["evaluated_result"] is False

    @pytest.mark.asyncio
    async def test_negated_exists_saved_backend_form(self) -> None:
        result = await condition(
            {"condition": "not (${data.optional} exists)", "namespace": {"data": {}}},
            None,
        )
        assert result["control"]["next_port"] == "true"

    @pytest.mark.asyncio
    async def test_starts_with(self) -> None:
        result = await condition(
            {"condition": '${username} startsWith "user_"', "namespace": {"username": "user_abc"}},
            None,
        )
        assert result["control"]["next_port"] == "true"

    @pytest.mark.asyncio
    async def test_is_empty(self) -> None:
        result = await condition({"condition": "${text} isEmpty", "namespace": {"text": ""}}, None)
        assert result["control"]["next_port"] == "true"


class TestConditionDoesNotBlockEventLoop:
    """Evaluation is offloaded to a thread so the worker event loop stays responsive.

    The ``matches`` operator runs a bounded subprocess synchronously; if that ran
    inline in this async activity it would block the shared event loop and every
    other concurrently executing activity (jewzaam review, PR #506). These tests
    assert the blocking work happens off the loop thread.
    """

    @pytest.mark.asyncio
    async def test_slow_evaluation_does_not_block_concurrent_coroutine(self) -> None:
        """A blocking evaluation must not stall other coroutines on the loop."""
        import contextlib

        block_seconds = 0.3
        ticks = 0

        async def _ticker() -> None:
            nonlocal ticks
            # Advances only while the event loop is free to schedule it.
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        def _blocking_eval(_expr: str, _ns: dict[str, Any]) -> bool:
            time.sleep(block_seconds)  # simulates the synchronous subprocess in `matches`
            return True

        with patch(
            "syntara.workflows.workflow_engine.activities.condition.safe_eval_with_namespace",
            side_effect=_blocking_eval,
        ):
            ticker_task = asyncio.create_task(_ticker())
            result = await condition({"condition": "${x} matches 'y'", "namespace": {"x": "y"}}, None)
            # Capture progress made *during* the evaluation, before draining the task.
            ticks_during_eval = ticks
            ticker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ticker_task

        assert result["control"]["next_port"] == "true"
        # With the fix, the ~0.3s evaluation runs off-loop and the ticker advances
        # many times meanwhile. If it ran inline, the loop would be blocked and the
        # ticker would still be at 0 when the evaluation returned.
        assert ticks_during_eval > 0

    @pytest.mark.asyncio
    async def test_evaluation_runs_off_the_event_loop_thread(self) -> None:
        """The evaluator executes on a worker thread, not the loop thread."""
        import threading

        loop_thread_id = threading.get_ident()  # the test coroutine runs on the loop thread
        seen_thread_ids: list[int] = []

        def _record_thread(_expr: str, _ns: dict[str, Any]) -> bool:
            seen_thread_ids.append(threading.get_ident())
            return True

        with patch(
            "syntara.workflows.workflow_engine.activities.condition.safe_eval_with_namespace",
            side_effect=_record_thread,
        ):
            await condition({"condition": "True", "namespace": {}}, None)

        assert seen_thread_ids
        assert seen_thread_ids[0] != loop_thread_id
