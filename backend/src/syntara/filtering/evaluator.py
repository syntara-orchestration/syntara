"""Prepare CEL once and evaluate generic input values without delivery side effects."""

import math

from celpy import Environment, celtypes
from celpy.celparser import CELParseError
from celpy.evaluation import CELEvalError, CELUnsupportedError

from syntara.filtering.exceptions import FilterValidationCode, FilterValidationError
from syntara.filtering.models.result import FilterErrorCode, FilterOutcome, FilterResult
from syntara.filtering.runtime import FilterRunner, is_missing_field_error, safe_matches
from syntara.filtering.validation import validate_expression_tree


def _to_cel(value: object) -> celtypes.Value:  # noqa: PLR0911 - explicit supported-type dispatch
    """Adapt JSON-compatible values without coercing objects or non-finite numbers."""
    if value is None:
        return None
    if isinstance(value, bool):
        return celtypes.BoolType(value)
    if isinstance(value, int):
        return celtypes.IntType(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            msg = "Filter input numbers must be finite"
            raise ValueError(msg)
        return celtypes.DoubleType(value)
    if isinstance(value, str):
        return celtypes.StringType(value)
    if isinstance(value, list):
        return celtypes.ListType([_to_cel(item) for item in value])
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            msg = "Filter input dictionary keys must be text"
            raise ValueError(msg)
        return celtypes.MapType({celtypes.StringType(key): _to_cel(item) for key, item in value.items()})
    msg = "Unsupported filter input type"
    raise TypeError(msg)


def _failure(code: FilterErrorCode) -> FilterResult:
    return FilterResult(outcome=FilterOutcome.EVALUATION_ERROR, error_code=code)


def _evaluation_error(error: CELEvalError) -> FilterResult:
    """Recognize only celpy's missing-map errors; other failures remain errors.

    Inspect the final error, after CEL's own boolean/presence handling. Do not
    search exception text for arbitrary input field names or convert subexpression
    errors to false before CEL has finished evaluating the expression.
    """
    cause_type = error.args[1] if len(error.args) > 1 else None
    if is_missing_field_error(error):
        return FilterResult(outcome=FilterOutcome.NO_MATCH)
    if cause_type is TypeError or cause_type is AttributeError:
        return _failure(FilterErrorCode.WRONG_TYPE)
    return _failure(FilterErrorCode.EVALUATION_FAILED)


class PreparedFilter:
    """A reusable interpreted CEL program, owned by one application thread.

    Bind only ``input`` and collection-macro locals. This library neither decodes
    transports nor owns sessions, audit events, workflow launches or commits.
    Preparation validates syntax/names; message-dependent types are evaluated
    by CEL. No dedicated expression resource limits are introduced here.
    """

    def __init__(self, expression: str) -> None:
        """Prepare one expression; reject configuration using sanitized errors."""
        if not isinstance(expression, str) or not expression.strip():
            raise FilterValidationError(FilterValidationCode.INVALID_EXPRESSION)
        environment = Environment(runner_class=FilterRunner)
        try:
            tree = environment.compile(expression)
            validate_expression_tree(tree)
            self._runner = environment.program(tree, functions={"matches": safe_matches})
        except CELParseError:
            raise FilterValidationError(FilterValidationCode.INVALID_SYNTAX) from None
        except RecursionError:
            raise FilterValidationError(FilterValidationCode.INVALID_EXPRESSION) from None

    def evaluate(self, value: object) -> FilterResult:
        """Evaluate a fresh activation without exposing values or exception contents."""
        try:
            adapted = _to_cel(value)
        except (TypeError, ValueError, ArithmeticError, RecursionError):
            return _failure(FilterErrorCode.INVALID_INPUT)
        try:
            result = self._runner.evaluate({"input": adapted})
        except CELEvalError as error:
            return _evaluation_error(error)
        except (TypeError, AttributeError):
            return _failure(FilterErrorCode.WRONG_TYPE)
        except (ArithmeticError, ValueError, LookupError, RecursionError, CELUnsupportedError):
            return _failure(FilterErrorCode.EVALUATION_FAILED)
        if not isinstance(result, celtypes.BoolType):
            return _failure(FilterErrorCode.NON_BOOLEAN)
        return FilterResult(outcome=FilterOutcome.MATCH if bool(result) else FilterOutcome.NO_MATCH)
