"""Cross-operator regressions for missing values and ranked CEL evaluation errors."""

import pytest

from syntara.filtering.evaluator import PreparedFilter
from syntara.filtering.models.result import FilterErrorCode, FilterOutcome

_BINARY_OPERATORS = ("+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=", "in")


@pytest.mark.parametrize("operator", _BINARY_OPERATORS)
@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("1", "input.missing"),
        ("input.missing", "1"),
        ("input.first", "input.second"),
        ("1", "input.meta.retries"),
    ],
)
def test_binary_operators_preserve_missing_operands(operator: str, left: str, right: str) -> None:
    result = PreparedFilter(f"({left}) {operator} ({right})").evaluate({})
    assert result.outcome == FilterOutcome.NO_MATCH
    assert result.error_code is None


@pytest.mark.parametrize("operator", _BINARY_OPERATORS)
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    ("failure", "error_code"),
    [
        ("input.text + 1", FilterErrorCode.WRONG_TYPE),
        ("input.text.matches(input.pattern)", FilterErrorCode.EVALUATION_FAILED),
    ],
)
def test_binary_operators_rank_mixed_operand_errors(
    *, operator: str, reverse: bool, failure: str, error_code: FilterErrorCode
) -> None:
    operands = ["input.missing", failure]
    if reverse:
        operands.reverse()
    expression = f"({operands[0]}) {operator} ({operands[1]})"
    result = PreparedFilter(expression).evaluate({"text": "value", "pattern": "["})
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == error_code


@pytest.mark.parametrize("operator", ["+", "-", "*", "/", "%"])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    ("prefix", "outcome"),
    [("true || ", FilterOutcome.MATCH), ("false && ", FilterOutcome.NO_MATCH)],
)
def test_outer_boolean_resolves_arithmetic_operand_errors(
    *, operator: str, reverse: bool, prefix: str, outcome: FilterOutcome
) -> None:
    operands = ["input.missing", "input.text + 1"]
    if reverse:
        operands.reverse()
    expression = prefix + f"(({operands[0]}) {operator} ({operands[1]}) == 1)"
    result = PreparedFilter(expression).evaluate({"text": "value"})
    assert result.outcome == outcome
    assert result.error_code is None


@pytest.mark.parametrize(
    "expression",
    [
        "1 + input.value == 5",
        "input.value + 1 == 5",
        "1 - input.value == -3",
        "input.value - 1 == 3",
        "2 * input.value == 8",
        "input.value * 2 == 8",
        "8 / input.value == 2",
        "input.value / 2 == 2",
        "9 % input.value == 1",
        "input.value % 3 == 1",
    ],
)
def test_valid_arithmetic_still_uses_cel_operations(expression: str) -> None:
    result = PreparedFilter(expression).evaluate({"value": 4})
    assert result.outcome == FilterOutcome.MATCH
    assert result.error_code is None


@pytest.mark.parametrize("expression", ["1 / input.zero == 1", "1 % input.zero == 1"])
@pytest.mark.parametrize(
    ("prefix", "outcome", "error_code"),
    [
        ("", FilterOutcome.EVALUATION_ERROR, FilterErrorCode.EVALUATION_FAILED),
        ("true || ", FilterOutcome.MATCH, None),
        ("false && ", FilterOutcome.NO_MATCH, None),
    ],
)
def test_zero_division_errors_remain_resolvable_cel_errors(
    expression: str, prefix: str, outcome: FilterOutcome, error_code: FilterErrorCode | None
) -> None:
    result = PreparedFilter(prefix + expression).evaluate({"zero": 0})
    assert result.outcome == outcome
    assert result.error_code == error_code


@pytest.mark.parametrize(
    "expression",
    [
        "-input.missing == 1",
        "!input.missing",
        "size(input.missing) == 0",
        "type(input.missing) == type(1)",
        "bool(input.missing)",
        'bytes(input.missing) == bytes("")',
        "double(input.missing) == 1.0",
        'duration(input.missing) == duration("1s")',
        "int(input.missing) == 1",
        'string(input.missing) == "value"',
        'timestamp(input.missing) == timestamp("2026-01-01T00:00:00Z")',
        "uint(input.missing) == 1u",
        "input.text.startsWith(input.missing)",
        "input.text.endsWith(input.missing)",
        "input.text.contains(input.missing)",
        "input.text.matches(input.missing)",
        "input.missing.size() == 1",
        "[input.missing, 1].size() == 2",
        "[1, input.missing].size() == 2",
        "input.items.all(item, 1 + item.missing == 2)",
    ],
)
def test_unary_function_method_and_list_paths_preserve_missing_errors(expression: str) -> None:
    result = PreparedFilter(expression).evaluate({"text": "value", "items": [{}]})
    assert result.outcome == FilterOutcome.NO_MATCH
    assert result.error_code is None


@pytest.mark.parametrize(
    "method",
    [
        "getDate",
        "getDayOfMonth",
        "getDayOfWeek",
        "getDayOfYear",
        "getFullYear",
        "getHours",
        "getMilliseconds",
        "getMinutes",
        "getMonth",
        "getSeconds",
    ],
)
def test_timestamp_methods_preserve_missing_timezone_arguments(method: str) -> None:
    expression = f'timestamp("2026-01-01T00:00:00Z").{method}(input.missing) == 1'
    result = PreparedFilter(expression).evaluate({})
    assert result.outcome == FilterOutcome.NO_MATCH
    assert result.error_code is None


@pytest.mark.parametrize("container", ["list", "method"])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    ("failure", "error_code"),
    [
        ("input.text + 1", FilterErrorCode.WRONG_TYPE),
        ("input.text.matches(input.pattern)", FilterErrorCode.EVALUATION_FAILED),
    ],
)
@pytest.mark.parametrize(
    ("prefix", "outcome"),
    [("", FilterOutcome.EVALUATION_ERROR), ("true || ", FilterOutcome.MATCH), ("false && ", FilterOutcome.NO_MATCH)],
)
def test_list_and_method_paths_rank_all_evaluated_errors(
    *,
    container: str,
    reverse: bool,
    failure: str,
    error_code: FilterErrorCode,
    prefix: str,
    outcome: FilterOutcome,
) -> None:
    operands = ["input.missing", failure]
    if reverse:
        operands.reverse()
    expression = (
        f"[{operands[0]}, {operands[1]}].size() == 2"
        if container == "list"
        else f"({operands[0]}).startsWith({operands[1]})"
    )
    result = PreparedFilter(prefix + expression).evaluate({"text": "value", "pattern": "["})
    assert result.outcome == outcome
    assert result.error_code == (error_code if outcome == FilterOutcome.EVALUATION_ERROR else None)


@pytest.mark.parametrize(
    ("expression", "error_code"),
    [
        ("has(input.value.field)", FilterErrorCode.WRONG_TYPE),
        ('has(input.value["field"])', FilterErrorCode.WRONG_TYPE),
        ("!has(input.value.field)", FilterErrorCode.WRONG_TYPE),
        ("has((1 / input.zero).field)", FilterErrorCode.EVALUATION_FAILED),
    ],
)
@pytest.mark.parametrize(
    ("prefix", "outcome"),
    [("", FilterOutcome.EVALUATION_ERROR), ("true || ", FilterOutcome.MATCH), ("false && ", FilterOutcome.NO_MATCH)],
)
def test_presence_checks_do_not_suppress_non_missing_errors(
    expression: str, error_code: FilterErrorCode, prefix: str, outcome: FilterOutcome
) -> None:
    result = PreparedFilter(prefix + expression).evaluate({"value": None, "zero": 0})
    assert result.outcome == outcome
    assert result.error_code == (error_code if outcome == FilterOutcome.EVALUATION_ERROR else None)


@pytest.mark.parametrize(
    ("expression", "error_code"),
    [
        ('{"missing": input.missing, [1]: 2}.size() == 2', FilterErrorCode.WRONG_TYPE),
        ('{[1]: 2, "missing": input.missing}.size() == 2', FilterErrorCode.WRONG_TYPE),
        ('{"same": input.missing, "same": 1}.size() == 1', FilterErrorCode.EVALUATION_FAILED),
        ('{"same": 1, "same": input.missing}.size() == 1', FilterErrorCode.EVALUATION_FAILED),
    ],
)
def test_missing_values_do_not_hide_map_key_failures(expression: str, error_code: FilterErrorCode) -> None:
    result = PreparedFilter(expression).evaluate({})
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == error_code


@pytest.mark.parametrize("expression", ["true && 1", "1 && true", "false || 1", "1 || false"])
def test_boolean_operators_do_not_return_non_boolean_operands(expression: str) -> None:
    result = PreparedFilter(expression).evaluate(None)
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.WRONG_TYPE
