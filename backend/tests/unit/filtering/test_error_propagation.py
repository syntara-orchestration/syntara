"""Native CEL C++ error propagation, without Python interpreter overrides."""

import pytest

from syntara.filtering.evaluator import PreparedFilter
from syntara.filtering.models.result import FilterErrorCode, FilterOutcome


@pytest.mark.parametrize("operator", ["+", "-", "*", "/", "%"])
@pytest.mark.parametrize("reverse", [False, True])
def test_arithmetic_propagates_missing_operands(operator: str, *, reverse: bool) -> None:
    operands = ["input.missing", "1"]
    if reverse:
        operands.reverse()
    result = PreparedFilter(f"({operands[0]}) {operator} ({operands[1]}) == 1").evaluate({})
    assert result.outcome == FilterOutcome.NO_MATCH
    assert result.error_code is None


@pytest.mark.parametrize("operator", ["&&", "||"])
@pytest.mark.parametrize("missing_first", [False, True])
def test_native_unresolved_error_selection_follows_operand_order(operator: str, *, missing_first: bool) -> None:
    operands = ["input.text + 1 == 2", "input.missing"]
    if missing_first:
        operands.reverse()
    result = PreparedFilter(f"({operands[0]}) {operator} ({operands[1]})").evaluate({"text": "x"})
    assert result.outcome == (FilterOutcome.NO_MATCH if missing_first else FilterOutcome.EVALUATION_ERROR)
    assert result.error_code == (None if missing_first else FilterErrorCode.WRONG_TYPE)


@pytest.mark.parametrize(
    ("expression", "outcome"),
    [
        ("false && input.missing", FilterOutcome.NO_MATCH),
        ("input.missing && false", FilterOutcome.NO_MATCH),
        ("true || input.missing", FilterOutcome.MATCH),
        ("input.missing || true", FilterOutcome.MATCH),
        ("false && (input.text + 1 == 2)", FilterOutcome.NO_MATCH),
        ("true || (input.text + 1 == 2)", FilterOutcome.MATCH),
        ("input.ok ? true : input.missing", FilterOutcome.MATCH),
        ("input.ok ? false : input.missing", FilterOutcome.NO_MATCH),
        ("input.missing ? true : false", FilterOutcome.NO_MATCH),
    ],
)
def test_native_boolean_and_conditional_resolution(expression: str, outcome: FilterOutcome) -> None:
    result = PreparedFilter(expression).evaluate({"text": "x", "ok": True})
    assert result.outcome == outcome
    assert result.error_code is None


@pytest.mark.parametrize(
    ("expression", "values", "outcome"),
    [
        ("input.all(item, item.ok)", [{}, {"ok": False}], FilterOutcome.NO_MATCH),
        ("input.exists(item, item.ok)", [{}, {"ok": True}], FilterOutcome.MATCH),
        ("input.all(item, item.ok)", [{}, {"ok": True}], FilterOutcome.NO_MATCH),
        ("input.exists(item, item.ok)", [{}, {"ok": False}], FilterOutcome.NO_MATCH),
        ("input.exists_one(item, item.ok)", [{}], FilterOutcome.NO_MATCH),
        ("input.map(item, item.ok).size() == 1", [{}], FilterOutcome.NO_MATCH),
    ],
)
def test_native_collection_error_resolution(
    expression: str, values: list[dict[str, object]], outcome: FilterOutcome
) -> None:
    result = PreparedFilter(expression).evaluate(values)
    assert result.outcome == outcome
    assert result.error_code is None


@pytest.mark.parametrize("missing_first", [False, True])
def test_native_collection_error_selection_is_not_python_priority(*, missing_first: bool) -> None:
    values = [{"ok": 1}, {}]
    if missing_first:
        values.reverse()
    result = PreparedFilter("input.all(item, item.ok)").evaluate(values)
    assert result.outcome == (FilterOutcome.NO_MATCH if missing_first else FilterOutcome.EVALUATION_ERROR)
    assert result.error_code == (None if missing_first else FilterErrorCode.WRONG_TYPE)


@pytest.mark.parametrize(
    "expression",
    [
        "!input.missing",
        "type(input.missing) == type(1)",
        "int(input.missing) == 1",
        "input.text.startsWith(input.missing)",
        "input.missing.size() == 1",
        "[input.missing, 1].size() == 2",
        '{"value": input.missing}.size() == 1',
    ],
)
def test_missing_errors_remain_unresolved_until_native_evaluation_finishes(expression: str) -> None:
    result = PreparedFilter(expression).evaluate({"text": "value"})
    assert result.outcome == FilterOutcome.NO_MATCH
    assert result.error_code is None
