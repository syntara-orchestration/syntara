"""Tests for switch activity."""

from typing import Any
from unittest.mock import patch

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.switch import switch

CASES_APPROVED_REJECTED = [
    {"port": "case_0", "label": "Approved", "condition": "${status} == 'approved'"},
    {"port": "case_1", "label": "Rejected", "condition": "${status} == 'rejected'"},
]


def _make_config(
    cases: list[dict[str, Any]] | None = None,
    default_port: str = "default",
    namespace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config: dict[str, Any] = {}
    if cases is not None:
        config["cases"] = cases
    config["default_port"] = default_port
    config["namespace"] = namespace or {}
    return config


class TestSwitchMatchesFirstCase:
    """First case evaluates truthy — routes to its port."""

    @pytest.mark.asyncio
    async def test_first_case_matches(self) -> None:
        config = _make_config(
            cases=CASES_APPROVED_REJECTED,
            namespace={"status": "approved"},
        )
        result = await switch(config, None)
        assert result["control"]["next_port"] == "case_0"

    @pytest.mark.asyncio
    async def test_first_case_output_status_completed(self) -> None:
        config = _make_config(
            cases=CASES_APPROVED_REJECTED,
            namespace={"status": "approved"},
        )
        result = await switch(config, None)
        assert result["output"]["matched_port"] == "case_0"


class TestSwitchMatchesSecondCase:
    """Second case evaluates truthy — routes to its port."""

    @pytest.mark.asyncio
    async def test_second_case_matches(self) -> None:
        config = _make_config(
            cases=CASES_APPROVED_REJECTED,
            namespace={"status": "rejected"},
        )
        result = await switch(config, None)
        assert result["control"]["next_port"] == "case_1"

    @pytest.mark.asyncio
    async def test_second_case_output(self) -> None:
        config = _make_config(
            cases=CASES_APPROVED_REJECTED,
            namespace={"status": "rejected"},
        )
        result = await switch(config, None)
        assert result["output"]["matched_port"] == "case_1"


class TestSwitchMultipleCasesFirstMatchWins:
    """Multiple truthy cases — first match wins."""

    @pytest.mark.asyncio
    async def test_first_truthy_case_wins(self) -> None:
        cases = [
            {"port": "case_0", "label": "Always true", "condition": "True"},
            {"port": "case_1", "label": "Also true", "condition": "True"},
        ]
        result = await switch(_make_config(cases=cases), None)
        assert result["control"]["next_port"] == "case_0"


class TestSwitchDefaultPort:
    """No case matches — routes to default port."""

    @pytest.mark.asyncio
    async def test_no_match_routes_to_default(self) -> None:
        config = _make_config(
            cases=CASES_APPROVED_REJECTED,
            namespace={"status": "pending"},
        )
        result = await switch(config, None)
        assert result["control"]["next_port"] == "default"

    @pytest.mark.asyncio
    async def test_no_match_output(self) -> None:
        config = _make_config(
            cases=CASES_APPROVED_REJECTED,
            namespace={"status": "pending"},
        )
        result = await switch(config, None)
        assert result["output"]["matched_port"] == "default"

    @pytest.mark.asyncio
    async def test_custom_default_port(self) -> None:
        config = _make_config(
            cases=[{"port": "case_0", "label": "Never", "condition": "False"}],
            default_port="fallback",
        )
        result = await switch(config, None)
        assert result["control"]["next_port"] == "fallback"


class TestSwitchMissingConfig:
    """Missing or empty cases raises ApplicationError."""

    @pytest.mark.asyncio
    async def test_cases_not_a_list_returns_failed(self) -> None:
        with pytest.raises(ApplicationError) as exc_info:
            await switch({"cases": "not_a_list", "namespace": {}}, None)
        assert "must be a list" in str(exc_info.value)
        assert exc_info.value.non_retryable is True

    @pytest.mark.asyncio
    async def test_cases_is_dict_returns_failed(self) -> None:
        with pytest.raises(ApplicationError) as exc_info:
            await switch({"cases": {"port": "val"}, "namespace": {}}, None)
        assert "dict" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_too_many_cases_returns_failed(self) -> None:
        cases = [{"port": f"case_{i}", "label": f"Case {i}", "condition": "True"} for i in range(101)]
        with pytest.raises(ApplicationError) as exc_info:
            await switch(_make_config(cases=cases), None)
        assert "exceeding the maximum" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_cases_returns_failed(self) -> None:
        with pytest.raises(ApplicationError) as exc_info:
            await switch(_make_config(cases=[]), None)
        assert exc_info.value.type == "ConfigError"

    @pytest.mark.asyncio
    async def test_case_key_matches_default_port_returns_failed(self) -> None:
        cases = [
            {"port": "default", "label": "Conflicts", "condition": "True"},
        ]
        with pytest.raises(ApplicationError) as exc_info:
            await switch(_make_config(cases=cases), None)
        assert "conflicts with default_port" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_case_key_matches_custom_default_port_returns_failed(self) -> None:
        cases = [
            {"port": "fallback", "label": "Conflicts", "condition": "True"},
        ]
        with pytest.raises(ApplicationError) as exc_info:
            await switch(_make_config(cases=cases, default_port="fallback"), None)
        assert "conflicts with default_port" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_missing_cases_key_returns_failed(self) -> None:
        with pytest.raises(ApplicationError) as exc_info:
            await switch({"namespace": {}}, None)
        assert "cases" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_duplicate_case_keys_returns_failed(self) -> None:
        cases = [
            {"port": "case_0", "label": "First", "condition": "True"},
            {"port": "case_0", "label": "Duplicate", "condition": "False"},
        ]
        with pytest.raises(ApplicationError) as exc_info:
            await switch(_make_config(cases=cases), None)
        assert "Duplicate" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_missing_cases_has_no_control(self) -> None:
        with pytest.raises(ApplicationError):
            await switch({"namespace": {}}, None)


class TestSwitchEmptyConditionSkipped:
    """Cases with empty condition strings are skipped."""

    @pytest.mark.asyncio
    async def test_empty_condition_skipped(self) -> None:
        cases = [
            {"port": "case_0", "label": "Empty", "condition": ""},
            {"port": "case_1", "label": "True", "condition": "True"},
        ]
        result = await switch(_make_config(cases=cases), None)
        assert result["control"]["next_port"] == "case_1"

    @pytest.mark.asyncio
    async def test_all_empty_conditions_goes_to_default(self) -> None:
        cases = [
            {"port": "case_0", "label": "Empty", "condition": ""},
            {"port": "case_1", "label": "Also empty", "condition": ""},
        ]
        result = await switch(_make_config(cases=cases), None)
        assert result["control"]["next_port"] == "default"


class TestSwitchEvaluationFailure:
    """Expression evaluation raises ApplicationError."""

    @pytest.mark.asyncio
    async def test_invalid_expression_returns_failed(self) -> None:
        with (
            patch(
                "syntara.workflows.workflow_engine.activities.switch.safe_eval_with_namespace",
                side_effect=ValueError("bad expression"),
            ),
            pytest.raises(ApplicationError) as exc_info,
        ):
            cases = [{"port": "case_0", "label": "Bad", "condition": "bad_expr"}]
            await switch(_make_config(cases=cases), None)
        assert exc_info.value.type == "SwitchEvaluationError"

    @pytest.mark.asyncio
    async def test_error_on_second_case_reports_correct_condition(self) -> None:
        """Error message should reference the condition that actually failed, not the first one."""
        with (
            patch(
                "syntara.workflows.workflow_engine.activities.switch.safe_eval_with_namespace",
                side_effect=[False, ValueError("fail on case 1")],
            ),
            pytest.raises(ApplicationError) as exc_info,
        ):
            cases = [
                {"port": "case_0", "label": "OK", "condition": "first_expr"},
                {"port": "case_1", "label": "Bad", "condition": "second_expr"},
            ]
            await switch(_make_config(cases=cases), None)
        assert "second_expr" in str(exc_info.value)
        assert "first_expr" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_missing_key_field_returns_failed(self) -> None:
        """Case without 'port' field should fail, not silently fabricate a port name."""
        cases = [{"label": "No key", "condition": "True"}]
        with pytest.raises(ApplicationError):
            await switch(_make_config(cases=cases), None)

    @pytest.mark.asyncio
    async def test_none_condition_value_skipped(self) -> None:
        """Case with condition=None should be skipped, not crash."""
        cases: list[dict[str, Any]] = [
            {"port": "case_0", "label": "None cond", "condition": None},
            {"port": "case_1", "label": "True", "condition": "True"},
        ]
        result = await switch(_make_config(cases=cases), None)
        assert result["control"]["next_port"] == "case_1"

    @pytest.mark.asyncio
    async def test_evaluation_error_has_no_control(self) -> None:
        with (
            patch(
                "syntara.workflows.workflow_engine.activities.switch.safe_eval_with_namespace",
                side_effect=ValueError("invalid"),
            ),
            pytest.raises(ApplicationError),
        ):
            cases = [{"port": "case_0", "label": "Bad", "condition": "x"}]
            await switch(_make_config(cases=cases), None)

    @pytest.mark.asyncio
    async def test_uncaught_exception_propagates(self) -> None:
        with (
            patch(
                "syntara.workflows.workflow_engine.activities.switch.safe_eval_with_namespace",
                side_effect=OSError("disk full"),
            ),
            pytest.raises(OSError, match="disk full"),
        ):
            cases = [{"port": "case_0", "label": "Bad", "condition": "x"}]
            await switch(_make_config(cases=cases), None)


class TestSwitchOutputMapping:
    """Output mapping integration."""

    @pytest.mark.asyncio
    async def test_none_output_config_returns_full_result(self) -> None:
        cases = [{"port": "case_0", "label": "True", "condition": "True"}]
        result = await switch(_make_config(cases=cases), None)
        assert "matched_port" in result["output"]

    @pytest.mark.asyncio
    async def test_empty_output_config_suppresses_fields(self) -> None:
        cases = [{"port": "case_0", "label": "True", "condition": "True"}]
        result = await switch(_make_config(cases=cases), {})
        assert result["output"] == {}

    @pytest.mark.asyncio
    async def test_output_mapping_does_not_affect_control(self) -> None:
        cases = [{"port": "case_0", "label": "True", "condition": "True"}]
        result = await switch(_make_config(cases=cases), {})
        assert result["control"] == {"next_port": "case_0"}

    @pytest.mark.asyncio
    async def test_output_mapping_ignored_on_failure(self) -> None:
        with pytest.raises(ApplicationError):
            await switch({"namespace": {}}, {"port": "${result.matched_port}"})


class TestSwitchControlData:
    """Control data contains correct next_port."""

    @pytest.mark.asyncio
    async def test_matched_port_control(self) -> None:
        cases = [{"port": "case_0", "label": "True", "condition": "True"}]
        result = await switch(_make_config(cases=cases), None)
        assert result["control"] == {"next_port": "case_0"}

    @pytest.mark.asyncio
    async def test_default_control(self) -> None:
        cases = [{"port": "case_0", "label": "False", "condition": "False"}]
        result = await switch(_make_config(cases=cases), None)
        assert result["control"] == {"next_port": "default"}


class TestSwitchWithNamespace:
    """Test switch evaluation with namespace variable lookup (Tier 2)."""

    @pytest.mark.asyncio
    async def test_string_equality(self) -> None:
        config = _make_config(
            cases=[{"port": "case_0", "label": "Match", "condition": "${status} == 'active'"}],
            namespace={"status": "active"},
        )
        result = await switch(config, None)
        assert result["control"]["next_port"] == "case_0"

    @pytest.mark.asyncio
    async def test_numeric_comparison(self) -> None:
        config = _make_config(
            cases=[{"port": "case_0", "label": "High", "condition": "${score} > 80"}],
            namespace={"score": 95},
        )
        result = await switch(config, None)
        assert result["control"]["next_port"] == "case_0"

    @pytest.mark.asyncio
    async def test_boolean_variable(self) -> None:
        config = _make_config(
            cases=[{"port": "case_0", "label": "Verified", "condition": "${verified} == True"}],
            namespace={"verified": True},
        )
        result = await switch(config, None)
        assert result["control"]["next_port"] == "case_0"

    @pytest.mark.asyncio
    async def test_in_operator(self) -> None:
        config = _make_config(
            cases=[{"port": "case_0", "label": "Critical", "condition": "'critical' in ${tags}"}],
            namespace={"tags": ["critical", "urgent"]},
        )
        result = await switch(config, None)
        assert result["control"]["next_port"] == "case_0"

    @pytest.mark.asyncio
    async def test_not_operator(self) -> None:
        config = _make_config(
            cases=[{"port": "case_0", "label": "Not done", "condition": "not ${done}"}],
            namespace={"done": False},
        )
        result = await switch(config, None)
        assert result["control"]["next_port"] == "case_0"

    @pytest.mark.asyncio
    async def test_nested_dict_access(self) -> None:
        config = _make_config(
            cases=[{"port": "case_0", "label": "High risk", "condition": "${order.risk} > 0.7"}],
            namespace={"order": {"risk": 0.9}},
        )
        result = await switch(config, None)
        assert result["control"]["next_port"] == "case_0"

    @pytest.mark.asyncio
    async def test_missing_variable_returns_failed(self) -> None:
        config = _make_config(
            cases=[{"port": "case_0", "label": "Missing", "condition": "${unknown} == 'x'"}],
            namespace={"status": "ok"},
        )
        with pytest.raises(ApplicationError) as exc_info:
            await switch(config, None)
        assert exc_info.value.type == "SwitchEvaluationError"

    @pytest.mark.asyncio
    async def test_multi_case_with_namespace(self) -> None:
        cases = [
            {"port": "case_0", "label": "Low", "condition": "${priority} == 'low'"},
            {"port": "case_1", "label": "High", "condition": "${priority} == 'high'"},
            {"port": "case_2", "label": "Critical", "condition": "${priority} == 'critical'"},
        ]
        config = _make_config(cases=cases, namespace={"priority": "high"})
        result = await switch(config, None)
        assert result["control"]["next_port"] == "case_1"


class TestSwitchComplexExpressions:
    """Test switch with complex AND/OR/NOT expressions (custom expression support)."""

    @pytest.mark.asyncio
    async def test_and_expression_both_true(self) -> None:
        """AND expression where both operands are truthy routes to case port."""
        cases = [
            {
                "port": "case_0",
                "label": "Urgent & Approved",
                "condition": "${priority} > 7 and ${approved} == True",
            },
        ]
        config = _make_config(cases=cases, namespace={"priority": 9, "approved": True})
        result = await switch(config, None)
        assert result["control"]["next_port"] == "case_0"
        assert result["output"]["matched_port"] == "case_0"

    @pytest.mark.asyncio
    async def test_and_expression_one_false_falls_to_default(self) -> None:
        """AND expression with one falsy operand falls through to default."""
        cases = [
            {
                "port": "case_0",
                "label": "Urgent & Approved",
                "condition": "${priority} > 7 and ${approved} == True",
            },
        ]
        config = _make_config(cases=cases, namespace={"priority": 9, "approved": False})
        result = await switch(config, None)
        assert result["control"]["next_port"] == "default"
        assert result["output"]["matched_port"] == "default"

    @pytest.mark.asyncio
    async def test_or_expression_second_true(self) -> None:
        """OR expression where second operand is truthy routes to case port."""
        cases = [
            {
                "port": "case_0",
                "label": "VIP or Premium",
                "condition": "${tier} == 'vip' or ${tier} == 'premium'",
            },
        ]
        config = _make_config(cases=cases, namespace={"tier": "premium"})
        result = await switch(config, None)
        assert result["control"]["next_port"] == "case_0"
        assert result["output"]["matched_port"] == "case_0"

    @pytest.mark.asyncio
    async def test_or_expression_both_false_falls_to_default(self) -> None:
        """OR expression where both operands are falsy falls through to default."""
        cases = [
            {
                "port": "case_0",
                "label": "VIP or Premium",
                "condition": "${tier} == 'vip' or ${tier} == 'premium'",
            },
        ]
        config = _make_config(cases=cases, namespace={"tier": "standard"})
        result = await switch(config, None)
        assert result["control"]["next_port"] == "default"
        assert result["output"]["matched_port"] == "default"

    @pytest.mark.asyncio
    async def test_nested_and_or_groups(self) -> None:
        """Nested (AND) OR expression evaluates grouped conditions correctly."""
        cases = [
            {
                "port": "case_0",
                "label": "Complex",
                "condition": "(${priority} > 5 and ${approved} == True) or ${is_admin} == True",
            },
        ]
        config = _make_config(
            cases=cases,
            namespace={"priority": 3, "approved": False, "is_admin": True},
        )
        result = await switch(config, None)
        assert result["control"]["next_port"] == "case_0"
        assert result["output"]["matched_port"] == "case_0"

    @pytest.mark.asyncio
    async def test_not_with_and_group(self) -> None:
        """Negated AND group evaluates correctly."""
        cases = [
            {
                "port": "case_0",
                "label": "Not blocked",
                "condition": "not (${status} == 'blocked' and ${retries} > 3)",
            },
        ]
        config = _make_config(cases=cases, namespace={"status": "blocked", "retries": 2})
        result = await switch(config, None)
        assert result["control"]["next_port"] == "case_0"
        assert result["output"]["matched_port"] == "case_0"

    @pytest.mark.asyncio
    async def test_complex_multi_case_first_match_wins(self) -> None:
        """Multiple cases with complex conditions — first match wins."""
        cases = [
            {
                "port": "case_0",
                "label": "High & Approved",
                "condition": "${priority} > 7 and ${approved} == True",
            },
            {
                "port": "case_1",
                "label": "VIP or Premium",
                "condition": "${tier} == 'vip' or ${tier} == 'premium'",
            },
            {
                "port": "case_2",
                "label": "Low risk",
                "condition": "${risk_score} < 0.3 and ${verified} == True",
            },
        ]
        config = _make_config(
            cases=cases,
            namespace={
                "priority": 5,
                "approved": False,
                "tier": "vip",
                "risk_score": 0.5,
                "verified": True,
            },
        )
        result = await switch(config, None)
        assert result["control"]["next_port"] == "case_1"
        assert result["output"]["matched_port"] == "case_1"

    @pytest.mark.asyncio
    async def test_complex_false_then_complex_true_routes_to_second(self) -> None:
        """First case complex expression is false, second case complex expression matches."""
        cases = [
            {
                "port": "case_0",
                "label": "High & Approved",
                "condition": "${priority} > 7 and ${approved} == True",
            },
            {
                "port": "case_1",
                "label": "Low & Verified",
                "condition": "${priority} <= 3 and ${verified} == True",
            },
        ]
        config = _make_config(
            cases=cases,
            namespace={"priority": 2, "approved": False, "verified": True},
        )
        result = await switch(config, None)
        assert result["control"]["next_port"] == "case_1"
        assert result["output"]["matched_port"] == "case_1"

    @pytest.mark.asyncio
    async def test_complex_expression_error_stops_evaluation(self) -> None:
        """Error in case_0 complex expression stops evaluation — case_1 never runs."""
        cases = [
            {
                "port": "case_0",
                "label": "Bad",
                "condition": "${priority} > 5 and ${missing_var} == True",
            },
            {
                "port": "case_1",
                "label": "Would match",
                "condition": "${status} == 'active'",
            },
        ]
        config = _make_config(cases=cases, namespace={"priority": 9, "status": "active"})
        with pytest.raises(ApplicationError) as exc_info:
            await switch(config, None)
        assert exc_info.value.type == "SwitchEvaluationError"
        assert "missing_var" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_and_short_circuit_skips_missing_var(self) -> None:
        """AND short-circuits when first operand is falsy — missing var in second operand is never evaluated."""
        cases = [
            {
                "port": "case_0",
                "label": "Skip",
                "condition": "${priority} > 100 and ${missing_var} == True",
            },
        ]
        config = _make_config(cases=cases, namespace={"priority": 5})
        result = await switch(config, None)
        assert result["control"]["next_port"] == "default"
        assert result["output"]["matched_port"] == "default"

    @pytest.mark.asyncio
    async def test_or_short_circuit_skips_missing_var(self) -> None:
        """OR short-circuits when first operand is truthy — missing var in second operand is never evaluated."""
        cases = [
            {
                "port": "case_0",
                "label": "Match",
                "condition": "${priority} > 5 or ${missing_var} == True",
            },
        ]
        config = _make_config(cases=cases, namespace={"priority": 9})
        result = await switch(config, None)
        assert result["control"]["next_port"] == "case_0"
        assert result["output"]["matched_port"] == "case_0"

    @pytest.mark.asyncio
    async def test_complex_expression_all_false_falls_to_default(self) -> None:
        """All cases with complex expressions are false — routes to default."""
        cases = [
            {
                "port": "case_0",
                "label": "High & Approved",
                "condition": "${priority} > 7 and ${approved} == True",
            },
            {
                "port": "case_1",
                "label": "VIP or Premium",
                "condition": "${tier} == 'vip' or ${tier} == 'premium'",
            },
        ]
        config = _make_config(
            cases=cases,
            namespace={"priority": 3, "approved": False, "tier": "standard"},
        )
        result = await switch(config, None)
        assert result["control"]["next_port"] == "default"
        assert result["output"]["matched_port"] == "default"
