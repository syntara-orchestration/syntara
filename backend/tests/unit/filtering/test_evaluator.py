"""Shared CEL behavior using the real parser and evaluator, without service I/O."""

import math
from unittest.mock import Mock

import pytest
from celpy import Environment

from syntara.filtering import evaluator as module
from syntara.filtering.evaluator import PreparedFilter
from syntara.filtering.exceptions import FilterValidationCode, FilterValidationError
from syntara.filtering.models.result import FilterErrorCode, FilterOutcome
from syntara.filtering.runtime import FilterRunner


@pytest.mark.parametrize(
    ("expression", "value"),
    [
        ('input == "critical"', "critical"),
        ('input == ""', ""),
        ('input.startsWith("prod-") && input.endsWith("-ready")', "prod-job-ready"),
        ('input.contains("middle")', "start-middle-end"),
        ('input.matches("^orders-[0-9]+$")', "orders-42"),
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
        ("has(input.value) && input.value == null", {"value": None}),
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
        ('input["missing"]["x"] == 1', {}),
        ("input.items[input.missing] == 1", {"items": [1]}),
        ("input.lookup[input.missing] == 1", {"lookup": {}}),
        ("input.first[input.second] == 1", {}),
        ('has(input.labels["env"])', {}),
        ('input.items.all(item, item.labels["env"] == "prod")', {"items": [{}]}),
        ("!input.missing", {}),
        ("has(input.missing)", {}),
        ("input.values.exists(item, item.missing == 1)", {"values": [{}]}),
    ],
)
def test_false_and_unresolved_missing_fields_do_not_match(expression: str, value: object) -> None:
    result = PreparedFilter(expression).evaluate(value)
    assert result.outcome == FilterOutcome.NO_MATCH
    assert result.error_code is None


@pytest.mark.parametrize(
    ("failure", "error_code"),
    [
        ("input.value + 1", FilterErrorCode.WRONG_TYPE),
        ("input.value.matches(input.pattern)", FilterErrorCode.EVALUATION_FAILED),
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    ("prefix", "outcome"),
    [
        ("", FilterOutcome.EVALUATION_ERROR),
        ("true || ", FilterOutcome.MATCH),
        ("false && ", FilterOutcome.NO_MATCH),
    ],
)
def test_indexing_preserves_mixed_operand_error_priority(
    *,
    failure: str,
    error_code: FilterErrorCode,
    reverse: bool,
    prefix: str,
    outcome: FilterOutcome,
) -> None:
    operands = ["input.missing", failure]
    if reverse:
        operands.reverse()
    expression = prefix + f"(({operands[0]})[{operands[1]}] == 1)"
    result = PreparedFilter(expression).evaluate({"value": "text", "pattern": "["})
    assert result.outcome == outcome
    assert result.error_code == (error_code if outcome == FilterOutcome.EVALUATION_ERROR else None)


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("input.missing == 1 || true", FilterOutcome.MATCH),
        ("true || input.missing == 1", FilterOutcome.MATCH),
        ("input.missing == 1 && false", FilterOutcome.NO_MATCH),
        ("false && input.missing == 1", FilterOutcome.NO_MATCH),
        ("!has(input.missing)", FilterOutcome.MATCH),
        ("has(input.missing) ? input.missing == 1 : true", FilterOutcome.MATCH),
        ("input.missing == 1 ? true : false", FilterOutcome.NO_MATCH),
    ],
)
def test_cel_boolean_and_presence_behavior_is_preserved(expression: str, expected: FilterOutcome) -> None:
    assert PreparedFilter(expression).evaluate({}).outcome == expected


@pytest.mark.parametrize("operator", ["&&", "||"])
@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("input.first", "input.second"),
        ('input.severity == "critical"', 'input.source == "payments"'),
        ("input.first.nested == 1", "input.second.nested == 2"),
    ],
)
def test_logical_operators_preserve_dual_missing_errors(operator: str, left: str, right: str) -> None:
    result = PreparedFilter(f"({left}) {operator} ({right})").evaluate({})
    assert result.outcome == FilterOutcome.NO_MATCH
    assert result.error_code is None


@pytest.mark.parametrize("operator", ["&&", "||"])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    ("failure", "error_code"),
    [
        ("input.value + 1 == 2", FilterErrorCode.WRONG_TYPE),
        ("input.value", FilterErrorCode.WRONG_TYPE),
        ("input.value.matches(input.pattern)", FilterErrorCode.EVALUATION_FAILED),
    ],
)
@pytest.mark.parametrize(
    ("prefix", "outcome"),
    [
        ("", FilterOutcome.EVALUATION_ERROR),
        ("true || ", FilterOutcome.MATCH),
        ("false && ", FilterOutcome.NO_MATCH),
    ],
)
def test_logical_operators_preserve_mixed_error_priority(
    *,
    operator: str,
    reverse: bool,
    failure: str,
    error_code: FilterErrorCode,
    prefix: str,
    outcome: FilterOutcome,
) -> None:
    operands = ["input.missing == 1", failure]
    if reverse:
        operands.reverse()
    expression = prefix + f"(({operands[0]}) {operator} ({operands[1]}))"
    result = PreparedFilter(expression).evaluate({"value": "text", "pattern": "["})
    assert result.outcome == outcome
    assert result.error_code == (error_code if outcome == FilterOutcome.EVALUATION_ERROR else None)


@pytest.mark.parametrize(
    ("operator", "decisive", "outcome"),
    [("&&", "false", FilterOutcome.NO_MATCH), ("||", "true", FilterOutcome.MATCH)],
)
@pytest.mark.parametrize("position", [0, 1, 2])
def test_decisive_boolean_resolves_chains_of_missing_errors(
    operator: str, decisive: str, outcome: FilterOutcome, position: int
) -> None:
    operands = ["input.first == 1", "input.second == 2"]
    operands.insert(position, decisive)
    result = PreparedFilter(f" {operator} ".join(operands)).evaluate({})
    assert result.outcome == outcome
    assert result.error_code is None


@pytest.mark.parametrize("value", [None, "", "text", 0, 1, 1.5, [], {}])
def test_non_boolean_values_are_errors(value: object) -> None:
    result = PreparedFilter("input").evaluate(value)
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.NON_BOOLEAN


@pytest.mark.parametrize(
    ("expression", "value"),
    [
        ("input.field == 1", "text"),
        ("input.value.field == 1", {"value": None}),
        ("input + 1 == 2", "text"),
        ('input.value["env"] == "prod"', {"value": None}),
        ('input.value["env"] == "prod"', {"value": 1}),
        ('input.value["env"] == "prod"', {"value": [1]}),
    ],
)
def test_wrong_types_remain_errors(expression: str, value: object) -> None:
    result = PreparedFilter(expression).evaluate(value)
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.WRONG_TYPE


@pytest.mark.parametrize(
    ("expression", "value"),
    [("1 / 0 == 0", None), ("input[10] == 1", [1])],
)
def test_other_evaluation_errors_are_not_missing_fields(expression: str, value: object) -> None:
    result = PreparedFilter(expression).evaluate(value)
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.EVALUATION_FAILED


@pytest.mark.parametrize("value", [object(), b"binary", {1: "value"}, math.nan, math.inf, {"value": math.inf}])
def test_unsupported_inputs_are_rejected_without_coercion(value: object) -> None:
    result = PreparedFilter("true").evaluate(value)
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.INVALID_INPUT


def test_nested_macro_variables_have_lexical_scope() -> None:
    prepared = PreparedFilter("input.groups.all(group, group.values.exists(value, value > group.minimum))")
    assert prepared.evaluate({"groups": [{"minimum": 1, "values": [1, 2]}]}).outcome == FilterOutcome.MATCH
    assert prepared.evaluate({"groups": [{"minimum": 2, "values": [1, 2]}]}).outcome == FilterOutcome.NO_MATCH


@pytest.mark.parametrize(
    ("expression", "code"),
    [
        ("", FilterValidationCode.INVALID_EXPRESSION),
        ("   ", FilterValidationCode.INVALID_EXPRESSION),
        ("input ==", FilterValidationCode.INVALID_SYNTAX),
        ("message.payload == 1", FilterValidationCode.UNSUPPORTED_VARIABLE),
        ("unknown(input)", FilterValidationCode.UNSUPPORTED_FUNCTION),
        ('input.custom("value")', FilterValidationCode.UNSUPPORTED_FUNCTION),
        ("input.values.reduce(total, item, 0, total + item)", FilterValidationCode.UNSUPPORTED_FUNCTION),
        ("input.values.all(item, true) && item.enabled", FilterValidationCode.UNSUPPORTED_VARIABLE),
        ("input.values.all(item, unknown.enabled)", FilterValidationCode.UNSUPPORTED_VARIABLE),
        ("input.values.all(input, true)", FilterValidationCode.INVALID_MACRO),
        ("input.values.all(item + 1, true)", FilterValidationCode.INVALID_MACRO),
        ("input.values.exists(item)", FilterValidationCode.INVALID_MACRO),
        ("input.values.map(item, true, item)", FilterValidationCode.INVALID_MACRO),
        ("has(input)", FilterValidationCode.INVALID_MACRO),
        ("has(input[0])", FilterValidationCode.INVALID_MACRO),
        ("has(input[true])", FilterValidationCode.INVALID_MACRO),
        ("has(input[null])", FilterValidationCode.INVALID_MACRO),
        ('has(input[b"event-type"])', FilterValidationCode.INVALID_MACRO),
        ("has(input[input.key])", FilterValidationCode.INVALID_MACRO),
        ('has(input["event-" + "type"])', FilterValidationCode.INVALID_MACRO),
        ('has(message["event-type"])', FilterValidationCode.UNSUPPORTED_VARIABLE),
        ("size(input, input)", FilterValidationCode.INVALID_EXPRESSION),
        ("input.contains()", FilterValidationCode.INVALID_EXPRESSION),
        ("input{}", FilterValidationCode.UNSUPPORTED_CONSTRUCT),
        (".size(input)", FilterValidationCode.UNSUPPORTED_CONSTRUCT),
    ],
)
def test_invalid_configuration_fails_during_preparation(expression: str, code: FilterValidationCode) -> None:
    with pytest.raises(FilterValidationError) as caught:
        PreparedFilter(expression)
    assert caught.value.code == code
    assert str(caught.value) == code.value


def test_preparation_does_not_claim_static_type_checking() -> None:
    prepared = PreparedFilter("input + 1 == 2")
    assert prepared.evaluate(1).outcome == FilterOutcome.MATCH
    assert prepared.evaluate("text").error_code == FilterErrorCode.WRONG_TYPE


def test_program_is_prepared_once_and_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    environment = Environment(runner_class=FilterRunner)
    compile_expression = Mock(wraps=environment.compile)
    monkeypatch.setattr(environment, "compile", compile_expression)
    factory = Mock(return_value=environment)
    monkeypatch.setattr(module, "Environment", factory)
    prepared = PreparedFilter("input == 1")
    assert [prepared.evaluate(value).outcome for value in [1, 2, 1]] == [
        FilterOutcome.MATCH,
        FilterOutcome.NO_MATCH,
        FilterOutcome.MATCH,
    ]
    factory.assert_called_once_with(runner_class=FilterRunner)
    compile_expression.assert_called_once_with("input == 1")


def test_results_and_validation_errors_exclude_input_contents() -> None:
    private_marker = "private-message-content"
    result = PreparedFilter("input.secret + 1 == 2").evaluate({"secret": private_marker})
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert private_marker not in result.model_dump_json()
    with pytest.raises(FilterValidationError) as caught:
        PreparedFilter(f'unknown("{private_marker}")')
    assert private_marker not in str(caught.value)


@pytest.mark.parametrize("macro", ["all", "exists", "exists_one", "filter"])
@pytest.mark.parametrize("predicate", [0, 1, "", "text", None, [], {}])
def test_collection_predicates_require_booleans(macro: str, predicate: object) -> None:
    expression = f"input.items.{macro}(item, item)"
    if macro == "filter":
        expression += ".size() > 0"
    result = PreparedFilter(expression).evaluate({"items": [predicate]})
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.WRONG_TYPE


@pytest.mark.parametrize("macro", ["all", "exists", "exists_one", "filter", "map"])
@pytest.mark.parametrize("receiver", [None, True, 1, "text"])
def test_collection_macros_reject_non_collection_receivers(macro: str, receiver: object) -> None:
    result = PreparedFilter(f"input.{macro}(item, true)").evaluate(receiver)
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.WRONG_TYPE


@pytest.mark.parametrize(
    "expression",
    [
        "input.items.exists_one(item, item.missing == 1)",
        "input.items.filter(item, item.missing == 1).size() > 0",
        "input.items.map(item, item.missing).size() > 0",
        "input.text.matches(input.missing)",
    ],
)
def test_nested_missing_errors_remain_no_match(expression: str) -> None:
    result = PreparedFilter(expression).evaluate({"items": [{}], "text": "value"})
    assert result.outcome == FilterOutcome.NO_MATCH
    assert result.error_code is None


@pytest.mark.parametrize(
    "condition",
    [
        "input.items.exists_one(item, item.missing == 1)",
        "input.items.filter(item, item.missing == 1).size() > 0",
        "input.items.map(item, item.missing).size() > 0",
    ],
)
@pytest.mark.parametrize(
    ("prefix", "outcome"),
    [("true || ", FilterOutcome.MATCH), ("false && ", FilterOutcome.NO_MATCH)],
)
def test_outer_boolean_results_can_resolve_nested_macro_errors(
    condition: str, prefix: str, outcome: FilterOutcome
) -> None:
    assert PreparedFilter(prefix + condition).evaluate({"items": [{}]}).outcome == outcome


@pytest.mark.parametrize(
    ("expression", "value", "outcome"),
    [
        ("input.items.all(item, item.ok)", {"items": [{}, {"ok": False}]}, FilterOutcome.NO_MATCH),
        ("input.items.exists(item, item.ok)", {"items": [{}, {"ok": True}]}, FilterOutcome.MATCH),
        ("input.items.exists_one(item, item)", {"items": [True, True]}, FilterOutcome.NO_MATCH),
        ("input.items.exists_one(item, item)", {"items": [False, True]}, FilterOutcome.MATCH),
        ("input.items.filter(item, item) == [true]", {"items": [False, True]}, FilterOutcome.MATCH),
        ("input.all(key, input[key] > 0)", {"first": 1, "second": 2}, FilterOutcome.MATCH),
    ],
)
def test_valid_collection_boolean_and_map_iteration_behavior(
    expression: str, value: object, outcome: FilterOutcome
) -> None:
    assert PreparedFilter(expression).evaluate(value).outcome == outcome


def test_nested_macros_keep_strict_predicate_validation() -> None:
    expression = "input.groups.all(group, group.items.exists_one(item, item))"
    result = PreparedFilter(expression).evaluate({"groups": [{"items": [1]}]})
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.WRONG_TYPE


def test_map_body_errors_cannot_be_hidden_by_size() -> None:
    result = PreparedFilter("input.items.map(item, item + 1).size() > 0").evaluate({"items": ["text"]})
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.WRONG_TYPE


@pytest.mark.parametrize("macro", ["all", "exists"])
def test_multiple_missing_predicates_remain_missing_errors(macro: str) -> None:
    result = PreparedFilter(f"input.items.{macro}(item, item.ok)").evaluate({"items": [{}, {}]})
    assert result.outcome == FilterOutcome.NO_MATCH
    assert result.error_code is None


@pytest.mark.parametrize(
    ("macro", "decisive", "outcome"),
    [("all", False, FilterOutcome.NO_MATCH), ("exists", True, FilterOutcome.MATCH)],
)
def test_later_boolean_resolves_multiple_missing_predicates(
    *, macro: str, decisive: bool, outcome: FilterOutcome
) -> None:
    result = PreparedFilter(f"input.items.{macro}(item, item.ok)").evaluate({"items": [{}, {}, {"ok": decisive}]})
    assert result.outcome == outcome
    assert result.error_code is None


@pytest.mark.parametrize("macro", ["all", "exists"])
@pytest.mark.parametrize(
    ("prefix", "outcome"),
    [("true || ", FilterOutcome.MATCH), ("false && ", FilterOutcome.NO_MATCH)],
)
def test_outer_boolean_resolves_multiple_predicate_errors(macro: str, prefix: str, outcome: FilterOutcome) -> None:
    result = PreparedFilter(prefix + f"input.items.{macro}(item, item.ok)").evaluate({"items": [{}, {}]})
    assert result.outcome == outcome
    assert result.error_code is None


@pytest.mark.parametrize("macro", ["all", "exists"])
def test_repeated_wrong_type_predicates_remain_type_errors(macro: str) -> None:
    result = PreparedFilter(f"input.items.{macro}(item, item.ok)").evaluate({"items": [{"ok": 1}, {"ok": "text"}]})
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.WRONG_TYPE


@pytest.mark.parametrize("macro", ["all", "exists"])
@pytest.mark.parametrize("items", [[{}, {"ok": 1}], [{"ok": 1}, {}]])
def test_missing_predicates_cannot_hide_wrong_types(macro: str, items: list[dict[str, object]]) -> None:
    result = PreparedFilter(f"input.items.{macro}(item, item.ok)").evaluate({"items": items})
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.WRONG_TYPE


@pytest.mark.parametrize("macro", ["all", "exists", "exists_one", "filter", "map"])
@pytest.mark.parametrize("reverse", [False, True])
def test_missing_predicates_cannot_hide_other_evaluation_failures(*, macro: str, reverse: bool) -> None:
    items = [{}, {"text": "value", "pattern": "["}]
    if reverse:
        items.reverse()
    expression = f"input.items.{macro}(item, item.text.matches(item.pattern))"
    if macro in {"filter", "map"}:
        expression += ".size() > 0"
    result = PreparedFilter(expression).evaluate({"items": items})
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.EVALUATION_FAILED


@pytest.mark.parametrize("macro", ["exists_one", "filter", "map"])
@pytest.mark.parametrize("items", [[{}, {"ok": 1}], [{"ok": 1}, {}]])
@pytest.mark.parametrize(
    ("prefix", "outcome", "error_code"),
    [
        ("", FilterOutcome.EVALUATION_ERROR, FilterErrorCode.WRONG_TYPE),
        ("true || ", FilterOutcome.MATCH, None),
        ("false && ", FilterOutcome.NO_MATCH, None),
    ],
)
def test_non_logical_macros_preserve_mixed_errors_and_outer_boolean_results(
    macro: str,
    items: list[dict[str, object]],
    prefix: str,
    outcome: FilterOutcome,
    error_code: FilterErrorCode | None,
) -> None:
    expression = f'input.items.{macro}(item, item.ok.startsWith("yes"))'
    if macro in {"filter", "map"}:
        expression += ".size() > 0"
    result = PreparedFilter(prefix + expression).evaluate({"items": items})
    assert result.outcome == outcome
    assert result.error_code == error_code


@pytest.mark.parametrize("macro", ["exists_one", "filter"])
@pytest.mark.parametrize("items", [[{}, {"ok": 1}], [{"ok": 1}, {}]])
def test_non_logical_predicates_cannot_hide_non_boolean_values(macro: str, items: list[dict[str, object]]) -> None:
    expression = f"input.items.{macro}(item, item.ok)"
    if macro == "filter":
        expression += ".size() > 0"
    result = PreparedFilter(expression).evaluate({"items": items})
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.WRONG_TYPE


@pytest.mark.parametrize(
    ("macro", "decisive", "outcome"),
    [("all", False, FilterOutcome.NO_MATCH), ("exists", True, FilterOutcome.MATCH)],
)
@pytest.mark.parametrize("reverse_errors", [False, True])
@pytest.mark.parametrize("decisive_first", [False, True])
def test_decisive_booleans_resolve_mixed_predicate_errors(
    *, macro: str, decisive: bool, outcome: FilterOutcome, reverse_errors: bool, decisive_first: bool
) -> None:
    items: list[dict[str, object]] = [{}, {"ok": 1}]
    if reverse_errors:
        items.reverse()
    items.insert(0 if decisive_first else len(items), {"ok": decisive})
    result = PreparedFilter(f"input.items.{macro}(item, item.ok)").evaluate({"items": items})
    assert result.outcome == outcome
    assert result.error_code is None


@pytest.mark.parametrize(
    ("prefix", "outcome"),
    [("true || ", FilterOutcome.MATCH), ("false && ", FilterOutcome.NO_MATCH)],
)
@pytest.mark.parametrize("macro", ["all", "exists"])
@pytest.mark.parametrize("items", [[{}, {"ok": 1}], [{"ok": 1}, {}]])
def test_outer_booleans_resolve_mixed_predicate_errors(
    prefix: str, outcome: FilterOutcome, macro: str, items: list[dict[str, object]]
) -> None:
    result = PreparedFilter(prefix + f"input.items.{macro}(item, item.ok)").evaluate({"items": items})
    assert result.outcome == outcome
    assert result.error_code is None


@pytest.mark.parametrize(
    "condition",
    [
        "input.items.exists_one(item, item.ok)",
        "input.items.filter(item, item.ok).size() > 0",
        "input.items.map(item, item.ok).size() > 0",
    ],
)
@pytest.mark.parametrize("items", [[{}, {"ok": True}], [{"ok": True}, {}], [{}, {"ok": False}], [{"ok": False}, {}]])
def test_boolean_values_do_not_resolve_missing_errors_in_non_short_circuiting_macros(
    condition: str, items: list[dict[str, object]]
) -> None:
    result = PreparedFilter(condition).evaluate({"items": items})
    assert result.outcome == FilterOutcome.NO_MATCH
    assert result.error_code is None


@pytest.mark.parametrize(
    ("expression", "value", "outcome"),
    [
        ('has(input["event-type"])', {"event-type": None}, FilterOutcome.MATCH),
        ('has(input["event-type"])', {"event-type": False}, FilterOutcome.MATCH),
        ('has(input["event-type"])', {"event-type": ""}, FilterOutcome.MATCH),
        ('has(input["event-type"])', {}, FilterOutcome.NO_MATCH),
        ("has(input['event-type'])", {"event-type": "created"}, FilterOutcome.MATCH),
        ('has(input[r"event-type"])', {"event-type": "created"}, FilterOutcome.MATCH),
        ('has(input["""event-type"""])', {"event-type": "created"}, FilterOutcome.MATCH),
        ('has(input["κλειδί"])', {"κλειδί": "value"}, FilterOutcome.MATCH),
        ('has(input["outer-key"]["inner-key"])', {"outer-key": {"inner-key": None}}, FilterOutcome.MATCH),
        ('has(input["outer-key"]["inner-key"])', {"outer-key": {}}, FilterOutcome.NO_MATCH),
        ('has(input["event-type"]) && input["event-type"] == "created"', {}, FilterOutcome.NO_MATCH),
        ('has(input["event-type"]) ? input["event-type"] == null : true', {}, FilterOutcome.MATCH),
    ],
)
def test_presence_checks_support_literal_string_keys(expression: str, value: object, outcome: FilterOutcome) -> None:
    result = PreparedFilter(expression).evaluate(value)
    assert result.outcome == outcome
    assert result.error_code is None


@pytest.mark.parametrize("condition", ["input.missing", "input.missing == 1"])
def test_ternary_preserves_missing_condition_errors(condition: str) -> None:
    result = PreparedFilter(condition + " ? true : false").evaluate({})
    assert result.outcome == FilterOutcome.NO_MATCH
    assert result.error_code is None


@pytest.mark.parametrize("condition", [None, 0, 1, "true", [], {}])
def test_ternary_requires_boolean_conditions(condition: object) -> None:
    result = PreparedFilter("input.condition ? true : false").evaluate({"condition": condition})
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.WRONG_TYPE


@pytest.mark.parametrize(
    ("expression", "value"),
    [
        ("input.condition ? true : input.missing", {"condition": True}),
        ("input.condition ? input.missing : true", {"condition": False}),
    ],
)
def test_ternary_does_not_evaluate_the_unchosen_branch(expression: str, value: object) -> None:
    result = PreparedFilter(expression).evaluate(value)
    assert result.outcome == FilterOutcome.MATCH
    assert result.error_code is None


@pytest.mark.parametrize(
    "expression",
    [
        '{"value": input.missing}.size() == 1',
        "{input.missing: 1}.size() == 1",
        '{"outer": {"value": input.missing}}.size() == 1',
        'input.items.map(item, {"value": item.missing}).size() > 0',
    ],
)
def test_map_literals_do_not_hide_missing_errors(expression: str) -> None:
    result = PreparedFilter(expression).evaluate({"items": [{}]})
    assert result.outcome == FilterOutcome.NO_MATCH
    assert result.error_code is None


@pytest.mark.parametrize(
    ("prefix", "outcome"),
    [("true || ", FilterOutcome.MATCH), ("false && ", FilterOutcome.NO_MATCH)],
)
def test_outer_boolean_can_resolve_map_literal_errors(prefix: str, outcome: FilterOutcome) -> None:
    result = PreparedFilter(prefix + '({"value": input.missing}.size() == 1)').evaluate({})
    assert result.outcome == outcome
    assert result.error_code is None


@pytest.mark.parametrize(
    "expression",
    ['{"value": input.value + 1}.size() == 1', "{[1]: 2}.size() == 1"],
)
def test_map_literals_preserve_wrong_type_errors(expression: str) -> None:
    result = PreparedFilter(expression).evaluate({"value": "text"})
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.WRONG_TYPE


@pytest.mark.parametrize(
    ("failure", "error_code"),
    [
        ("input.value + 1", FilterErrorCode.WRONG_TYPE),
        ("input.value.matches(input.pattern)", FilterErrorCode.EVALUATION_FAILED),
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("errors_in_keys", [False, True])
@pytest.mark.parametrize(
    ("prefix", "outcome"),
    [
        ("", FilterOutcome.EVALUATION_ERROR),
        ("true || ", FilterOutcome.MATCH),
        ("false && ", FilterOutcome.NO_MATCH),
    ],
)
def test_map_literals_preserve_mixed_error_priority(
    *,
    failure: str,
    error_code: FilterErrorCode,
    reverse: bool,
    errors_in_keys: bool,
    prefix: str,
    outcome: FilterOutcome,
) -> None:
    entries = (
        ["input.missing: true", f"{failure}: true"]
        if errors_in_keys
        else ['"missing": input.missing', f'"failed": {failure}']
    )
    if reverse:
        entries.reverse()
    expression = prefix + "({" + ", ".join(entries) + "}.size() == 2)"
    result = PreparedFilter(expression).evaluate({"value": "text", "pattern": "["})
    assert result.outcome == outcome
    assert result.error_code == (error_code if outcome == FilterOutcome.EVALUATION_ERROR else None)


def test_map_literals_reject_duplicate_keys() -> None:
    result = PreparedFilter('{"value": 1, "value": 2}.size() == 1').evaluate({})
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == FilterErrorCode.EVALUATION_FAILED


def test_map_literals_keep_valid_null_values() -> None:
    result = PreparedFilter('{"value": input.value}.value == null').evaluate({"value": None})
    assert result.outcome == FilterOutcome.MATCH
    assert result.error_code is None
