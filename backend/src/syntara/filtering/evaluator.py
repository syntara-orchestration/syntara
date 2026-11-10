"""Compile and evaluate CEL through the official C++ engine's Python bindings."""

import math
import re
from typing import cast

from cel_expr_python import cel  # type: ignore[import-untyped]  # Native wheel has no py.typed marker.

from syntara.filtering.exceptions import FilterValidationCode, FilterValidationError
from syntara.filtering.models.result import FilterErrorCode, FilterOutcome, FilterResult

_MIN_INT = -(2**63)
_MAX_INT = 2**63 - 1
_COMPILER_DIAGNOSTIC = re.compile(r"^INVALID_ARGUMENT: ERROR: <input>:(\d+):(\d+): (.*)$")


def _validate_input(value: object) -> None:
    """Reject coercion, unsupported objects and values outside CEL's JSON domain."""
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        value.encode("utf-8", errors="strict")
        return
    if isinstance(value, int):
        if not _MIN_INT <= value <= _MAX_INT:
            message = "Filter input integer is outside the CEL int range"
            raise ValueError(message)
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            message = "Filter input numbers must be finite"
            raise ValueError(message)
        return
    if isinstance(value, list):
        for item in value:
            _validate_input(item)
        return
    if isinstance(value, dict):
        _validate_mapping(value)
        return
    message = "Unsupported filter input type"
    raise TypeError(message)


def _validate_mapping(value: dict[object, object]) -> None:
    """Validate JSON dictionary keys and recursively validate their values."""
    for key, item in value.items():
        if not isinstance(key, str):
            message = "Filter input dictionary keys must be text"
            raise TypeError(message)
        _validate_input(key)
        _validate_input(item)


def _compile_error(expression: str, error: Exception) -> FilterValidationCode:
    """Classify only the native diagnostic header; never emit its source excerpt."""
    header = str(error).partition("\n")[0]
    diagnostic = _COMPILER_DIAGNOSTIC.fullmatch(header)
    if diagnostic is None:
        return FilterValidationCode.INVALID_EXPRESSION
    line, column, message = diagnostic.groups()
    if message.startswith("Syntax error:"):
        return FilterValidationCode.INVALID_SYNTAX
    if message.startswith("has() argument"):
        return FilterValidationCode.INVALID_MACRO
    if message.startswith("undeclared reference to "):
        lines = expression.splitlines()
        line_index, column_index = int(line) - 1, int(column) - 1
        is_call = (
            0 <= line_index < len(lines)
            and 0 <= column_index < len(lines[line_index])
            and lines[line_index][column_index] == "("
        )
        return FilterValidationCode.UNSUPPORTED_FUNCTION if is_call else FilterValidationCode.UNSUPPORTED_VARIABLE
    return FilterValidationCode.INVALID_EXPRESSION


def compile_expression(expression: str) -> cel.Expression:
    """Create one native checked program with only input available as a root variable."""
    environment = cel.NewEnv(variables={"input": cel.Type.DYN})
    try:
        program = environment.compile(expression)
    except (RuntimeError, ValueError, LookupError, RecursionError) as error:
        diagnostic = _COMPILER_DIAGNOSTIC.fullmatch(str(error).partition("\n")[0])
        raise FilterValidationError(
            _compile_error(expression, error),
            line=int(diagnostic[1]) if diagnostic is not None else None,
            column=int(diagnostic[2]) if diagnostic is not None else None,
        ) from None
    if program.return_type() not in (cel.Type.BOOL, cel.Type.DYN):
        raise FilterValidationError(FilterValidationCode.NON_BOOLEAN)
    return program


def _failure(code: FilterErrorCode) -> FilterResult:
    return FilterResult(outcome=FilterOutcome.EVALUATION_ERROR, error_code=code)


def _native_error(value: object) -> FilterResult:
    """Map pinned native status prefixes to safe outcomes, never returning raw details.

    Inspect an ERROR value only after native CEL has resolved boolean logic.
    Native CEL decides which unresolved error wins when several operands fail.
    Unrecognized statuses fail closed as evaluation errors rather than no-match.
    """
    if isinstance(value, str):
        if value.startswith("NOT_FOUND: Key not found in map : "):
            return FilterResult(outcome=FilterOutcome.NO_MATCH)
        if value.startswith("UNKNOWN: No matching overloads found : "):
            return _failure(FilterErrorCode.WRONG_TYPE)
        if value == "INVALID_ARGUMENT: Applying SELECT to non-message type" or value.startswith(
            "INVALID_ARGUMENT: Invalid container type: "
        ):
            return _failure(FilterErrorCode.WRONG_TYPE)
    return _failure(FilterErrorCode.EVALUATION_FAILED)


class PreparedFilter:
    """A reusable native C++ CEL program with per-evaluation input and arena lifetime.

    The compiler checks syntax, names and statically known types. The input root
    is dynamic; message-dependent types remain runtime checks. This adapter owns
    no transport, database session, audit event or delivery acknowledgement.
    """

    def __init__(self, expression: str | None = None) -> None:
        """Prepare once and discard native diagnostics containing source text."""
        if expression is not None and not isinstance(expression, str):
            raise FilterValidationError(FilterValidationCode.INVALID_EXPRESSION)
        self._program = compile_expression(expression) if expression is not None and expression.strip() else None

    @property
    def serialized(self) -> bytes | None:
        """Expose the compiler's checked AST for conservative preparation plans."""
        return None if self._program is None else cast("bytes", self._program.serialize())

    @classmethod
    def from_serialized(cls, serialized: bytes) -> "PreparedFilter":
        """Reuse a checked native subtree; never compile generated CEL source."""
        prepared = cls()
        prepared._program = cel.NewEnv(variables={"input": cel.Type.DYN}).deserialize(serialized)
        return prepared

    def is_definitely_false(self, value: object) -> bool:
        """Reject an extracted conjunct only on boolean false, never on error."""
        if self._program is None:
            return False
        try:
            _validate_input(value)
            result = self._program.eval(data={"input": value})
            return bool(result.type() == cel.Type.BOOL and result.value() is False)
        except (RuntimeError, TypeError, ValueError, LookupError, ArithmeticError, RecursionError):
            return False

    def evaluate(self, value: object) -> FilterResult:
        """Use a fresh native activation/arena; return no native values or diagnostics."""
        if self._program is None:
            return FilterResult(outcome=FilterOutcome.MATCH)
        try:
            _validate_input(value)
        except (TypeError, ValueError, ArithmeticError, RecursionError):
            return _failure(FilterErrorCode.INVALID_INPUT)
        try:
            result = self._program.eval(data={"input": value})
            result_type = result.type()
            if result_type == cel.Type.ERROR:
                return _native_error(result.value())
            if result_type != cel.Type.BOOL:
                return _failure(FilterErrorCode.NON_BOOLEAN)
            return FilterResult(outcome=FilterOutcome.MATCH if result.value() is True else FilterOutcome.NO_MATCH)
        except (RuntimeError, TypeError, ValueError, LookupError, ArithmeticError, RecursionError):
            return _failure(FilterErrorCode.EVALUATION_FAILED)
