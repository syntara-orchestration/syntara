"""Shared filter contracts exercised through the real CEL C++ binding."""

import math
from unittest.mock import Mock

import pytest
from cel_expr_python import cel  # type: ignore[import-untyped]

from syntara.filtering import evaluator as module
from syntara.filtering.evaluator import PreparedFilter
from syntara.filtering.exceptions import FilterValidationCode, FilterValidationError
from syntara.filtering.models.result import FilterErrorCode, FilterOutcome


@pytest.mark.parametrize(
    ("expression", "value"),
    [
        ('input == "critical"', "critical"),
        ('input == ""', ""),
        ('input.startsWith("prod-") && input.endsWith("-ready")', "prod-job-ready"),
        ('input.contains("middle")', "start-middle-end"),
        ('input.matches("orders-[0-9]+")', "orders-42"),
        ('input.severity == "critical"', {"severity": "critical"}),
        ('input["event-type"] == "created"', {"event-type": "created"}),
        ("input[0] == 2 && size(input) == 2", [2, 3]),
        ("input == true", True),
        ("input == false", False),
        ("input == null", None),
        ("input + 1 == 3", 2),
        ("input > 1.0", 1.5),
        ("int(input) == 2", "2"),
        ("double(input) == 2.5", "2.5"),
        ("type(input) == type(1)", 2),
        ("input.values.all(item, item > 0)", {"values": [1, 2]}),
        ("input.values.exists(item, item == 2)", {"values": [1, 2]}),
        ("input.values.exists_one(item, item == 2)", {"values": [1, 2]}),
        ("input.values.map(item, item + 1) == [2, 3]", {"values": [1, 2]}),
        ("input.values.filter(item, item > 1) == [2]", {"values": [1, 2]}),
        ("input.values.map(item, item > 1, item + 1) == [3]", {"values": [1, 2]}),
        ("has(input.value) && input.value == null", {"value": None}),
        ('"event-type" in input && input["event-type"] == "created"', {"event-type": "created"}),
        ('input == "café"', "café"),
        ('string(input) == "2"', 2),
        ("bool(input)", True),
        ('bytes(input) == b"hello"', "hello"),
        ('duration(input) == duration("1s")', "1s"),
        ("timestamp(input).getFullYear() == 2026", "2026-01-01T00:00:00Z"),
        ("uint(input) == 2u", 2),
        (
            "input.groups.all(group, group.values.all(item, item >= group.minimum))",
            {"groups": [{"minimum": 1, "values": [1, 2]}]},
        ),
    ],
)
def test_supported_generic_inputs(expression: str, value: object) -> None:
    result = PreparedFilter(expression).evaluate(value)
    assert result.outcome == FilterOutcome.MATCH
    assert result.error_code is None


@pytest.mark.parametrize(
    ("expression", "value"),
    [
        ('input == "critical"', "warning"),
        ("input", False),
        ("input.missing == 1", {}),
        ('input["missing"] == 1', {}),
        ("input.missing.nested == 1", {}),
        ('input.missing["x"] == 1', {}),
        ('input.labels["env"] == "prod"', {}),
        ("!input.missing", {}),
        ("has(input.missing)", {}),
        ("input.values.exists(item, item.missing == 1)", {"values": [{}]}),
        ("input.missing ? true : false", {}),
        ('"event-type" in input', {}),
    ],
)
def test_false_and_unresolved_missing_fields_do_not_match(expression: str, value: object) -> None:
    result = PreparedFilter(expression).evaluate(value)
    assert result.outcome == FilterOutcome.NO_MATCH
    assert result.error_code is None


@pytest.mark.parametrize("value", [None, 1, 1.5, "true", [], {}])
def test_non_boolean_results_remain_errors(value: object) -> None:
    result = PreparedFilter("input").evaluate(value)
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.NON_BOOLEAN


@pytest.mark.parametrize(
    ("expression", "value"),
    [
        ("input + 1 == 2", "text"),
        ("input.field", None),
        ("input.field", 1),
        ('input["field"]', None),
        ("input.startsWith('x')", 1),
        ("has(input.field)", None),
    ],
)
def test_message_dependent_wrong_types_are_errors(expression: str, value: object) -> None:
    result = PreparedFilter(expression).evaluate(value)
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.WRONG_TYPE


@pytest.mark.parametrize("macro", ["all", "exists", "exists_one"])
def test_collection_predicates_require_actual_booleans(macro: str) -> None:
    result = PreparedFilter(f"input.values.{macro}(item, item.ok)").evaluate({"values": [{"ok": 1}]})
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.WRONG_TYPE


@pytest.mark.parametrize(
    ("expression", "value"),
    [
        ("input.text.matches(input.pattern)", {"text": "x", "pattern": "["}),
        ("1 / input == 1", 0),
        ("input[99] == 1", [0]),
        ("int(input) == 1", "not-an-int"),
        ('timestamp(input) == timestamp("2026-01-01T00:00:00Z")', "not-a-time"),
    ],
)
def test_other_native_errors_are_not_missing_fields(expression: str, value: object) -> None:
    result = PreparedFilter(expression).evaluate(value)
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.EVALUATION_FAILED


@pytest.mark.parametrize(
    "value",
    [
        b"bytes",
        (1, 2),
        {1: "number-key"},
        {"nested": object()},
        math.nan,
        math.inf,
        -math.inf,
        2**63,
        -(2**63) - 1,
        "\ud800",
    ],
)
def test_unsupported_inputs_are_not_coerced(value: object) -> None:
    result = PreparedFilter("true").evaluate(value)
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.INVALID_INPUT


def test_recursive_input_returns_safe_invalid_input() -> None:
    value: list[object] = []
    value.append(value)
    assert PreparedFilter("true").evaluate(value).error_code == FilterErrorCode.INVALID_INPUT


@pytest.mark.parametrize(
    "expression",
    [
        "input ==",
        "message.payload == 1",
        "unknown(input)",
        'input.custom("value")',
        "input.values.all(item, true) && item.enabled",
        "input.values.all(item, unknown.enabled)",
        "has(input)",
        'has(input["key"])',
        "true && 1",
        "1 + 'text' == 2",
        "input{}",
        "42",
        "'text'",
    ],
)
def test_invalid_configuration_is_rejected_by_native_compiler(expression: str) -> None:
    with pytest.raises(FilterValidationError) as caught:
        PreparedFilter(expression)
    assert isinstance(caught.value.code, FilterValidationCode)
    assert str(caught.value) == caught.value.code.value


def test_dynamic_input_types_are_still_checked_at_evaluation() -> None:
    prepared = PreparedFilter("input + 1 == 2")
    assert prepared.evaluate(1).outcome == FilterOutcome.MATCH
    assert prepared.evaluate("text").error_code == FilterErrorCode.WRONG_TYPE


def test_native_program_is_compiled_once_and_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    compiler = Mock(wraps=module.compile_expression)
    monkeypatch.setattr(module, "compile_expression", compiler)
    prepared = PreparedFilter("input == 1")
    assert [prepared.evaluate(value).outcome for value in [1, 2, 1]] == [
        FilterOutcome.MATCH,
        FilterOutcome.NO_MATCH,
        FilterOutcome.MATCH,
    ]
    compiler.assert_called_once_with("input == 1")
    assert isinstance(prepared._program, cel.Expression)


def test_evaluations_do_not_reuse_previous_activation_values() -> None:
    prepared = PreparedFilter("input.ok")
    assert prepared.evaluate({"ok": True}).outcome == FilterOutcome.MATCH
    assert prepared.evaluate({}).outcome == FilterOutcome.NO_MATCH
    assert prepared.evaluate({"ok": False}).outcome == FilterOutcome.NO_MATCH
    assert prepared.evaluate({"ok": True}).outcome == FilterOutcome.MATCH


def test_results_and_validation_errors_exclude_input_contents() -> None:
    sample_text = "private-message-content"
    result = PreparedFilter("input.secret + 1 == 2").evaluate({"secret": sample_text})
    assert result.error_code == FilterErrorCode.WRONG_TYPE
    assert sample_text not in result.model_dump_json()
    with pytest.raises(FilterValidationError) as caught:
        PreparedFilter(f'unknown("{sample_text}")')
    assert sample_text not in str(caught.value)


def test_customer_strings_cannot_impersonate_native_error_statuses() -> None:
    result = PreparedFilter("input").evaluate('NOT_FOUND: Key not found in map : "secret"')
    assert result.error_code == FilterErrorCode.NON_BOOLEAN


def test_unknown_native_status_fails_closed() -> None:
    assert module._native_error("NOT_FOUND: other failure").error_code == FilterErrorCode.EVALUATION_FAILED


@pytest.mark.parametrize("expression", [None, "", "  ", "\n\t"])
def test_blank_filter_matches_without_compiling(expression: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    compiler = Mock(side_effect=AssertionError("A blank filter must not compile"))
    monkeypatch.setattr(module, "compile_expression", compiler)
    assert PreparedFilter(expression).evaluate({}).outcome == FilterOutcome.MATCH
    compiler.assert_not_called()


def test_compiler_diagnostics_keep_only_safe_location() -> None:
    with pytest.raises(FilterValidationError) as caught:
        PreparedFilter("input.value >")
    assert caught.value.line == 1
    assert caught.value.column is not None
    assert "input.value" not in str(caught.value)


@pytest.mark.parametrize(
    ("pattern", "text", "outcome"),
    [
        ("orders-[0-9]+", "prefix-orders-42-suffix", FilterOutcome.MATCH),
        ("^orders-[0-9]+$", "prefix-orders-42-suffix", FilterOutcome.NO_MATCH),
        ("^orders-[0-9]+$", "orders-42", FilterOutcome.MATCH),
        ("orders", "ORDERS", FilterOutcome.NO_MATCH),
        ("(?i)orders", "ORDERS", FilterOutcome.MATCH),
        (r"^service\.example$", "service.example", FilterOutcome.MATCH),
    ],
)
def test_standard_re2_matching_semantics(pattern: str, text: str, outcome: FilterOutcome) -> None:
    result = PreparedFilter("input.text.matches(input.pattern)").evaluate({"text": text, "pattern": pattern})
    assert result.outcome == outcome


@pytest.mark.parametrize("pattern", ["[", "(?=orders)orders", "(?<=prefix)orders", r"(orders)\1"])
def test_invalid_or_unsupported_re2_patterns_are_safe_evaluation_errors(pattern: str) -> None:
    result = PreparedFilter("input.text.matches(input.pattern)").evaluate({"text": "ordersorders", "pattern": pattern})
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.EVALUATION_FAILED
    assert pattern not in result.model_dump_json()


@pytest.mark.parametrize("value", [-(2**63), -(2**53) - 1, 2**53 + 1, 2**63 - 1])
def test_native_integers_preserve_precision_and_signed_boundaries(value: int) -> None:
    expression = f"input.value == {value} && input.value != {value - 1 if value > -(2**63) else value + 1}"
    assert PreparedFilter(expression).evaluate({"value": value}).outcome == FilterOutcome.MATCH


def test_native_integer_overflow_is_an_error_without_rounding() -> None:
    result = PreparedFilter("input + 1 > input").evaluate(2**63 - 1)
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.EVALUATION_FAILED
