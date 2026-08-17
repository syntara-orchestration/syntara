"""Expression resolver for workflow variables and outputs.

This module provides expression resolution for workflow definitions, supporting
references to inputs, variables, activity outputs, and loop iteration variables.
"""

import ast
import re
from typing import Any, Literal, cast

# Type alias for comparison operators
ComparisonOp = Literal["==", "!=", ">=", "<=", ">", "<"]

# Supported comparison operators
SUPPORTED_OPERATORS: set[str] = {"==", "!=", ">=", "<=", ">", "<"}

# Minimum parts required for condition expression parsing
MIN_CONDITION_PARTS = 2


_SAFE_COMPARISON_OPS: dict[type[ast.cmpop], str] = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Gt: ">",
    ast.Lt: "<",
    ast.GtE: ">=",
    ast.LtE: "<=",
}


def _safe_eval_node(node: ast.expr) -> object:
    """Evaluate an AST node, allowing only safe constructs.

    Supports constants (bool, int, float, str, None), unary minus/not,
    comparisons (==, !=, >, <, >=, <=), and boolean operators (and, or).

    Raises:
        ValueError: If the node contains unsupported constructs.

    """
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.UnaryOp):
        return _eval_unary_op(node)

    if isinstance(node, ast.Compare):
        return _eval_compare(node)

    if isinstance(node, ast.BoolOp):
        values = [_safe_eval_node(v) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
        msg = f"Unsupported boolean operator: {type(node.op).__name__}"
        raise ValueError(msg)

    msg = f"Unsupported expression type: {type(node).__name__}"
    raise ValueError(msg)


def _eval_unary_op(node: ast.UnaryOp) -> object:
    """Evaluate a unary operation node."""
    operand = _safe_eval_node(node.operand)
    if isinstance(node.op, ast.USub):
        return -operand  # type: ignore[operator]
    if isinstance(node.op, ast.Not):
        return not operand
    msg = f"Unsupported unary operator: {type(node.op).__name__}"
    raise ValueError(msg)


def _eval_compare(node: ast.Compare) -> bool:
    """Evaluate a comparison chain node."""
    left = _safe_eval_node(node.left)
    for op, comparator in zip(node.ops, node.comparators, strict=True):
        if type(op) not in _SAFE_COMPARISON_OPS:
            msg = f"Unsupported comparison operator: {type(op).__name__}"
            raise ValueError(msg)
        right = _safe_eval_node(comparator)
        op_str = _SAFE_COMPARISON_OPS[type(op)]
        if not _compare(left, right, cast("ComparisonOp", op_str)):
            return False
        left = right
    return True


def _to_numeric(val: object) -> float:
    """Convert a value to float for numeric comparison.

    Handles bool before str to avoid float("True") ValueError.
    """
    if isinstance(val, bool):
        return float(val)
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val))
    except (ValueError, TypeError) as exc:
        msg = f"Cannot convert {val!r} to numeric for comparison"
        raise ValueError(msg) from exc


def _compare(left: object, right: object, op: ComparisonOp) -> bool:
    """Compare two values with the given operator."""
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    # For ordering comparisons, both must be numeric
    try:
        left_num = _to_numeric(left)
        right_num = _to_numeric(right)
    except (ValueError, TypeError) as exc:
        msg = f"Cannot compare non-numeric values with '{op}': {left!r}, {right!r}"
        raise ValueError(msg) from exc
    if op == ">":
        return left_num > right_num
    if op == "<":
        return left_num < right_num
    if op == ">=":
        return left_num >= right_num
    return left_num <= right_num


def safe_eval_condition(expression: str) -> bool:
    """Safely evaluate a condition expression without eval().

    Supports boolean literals, string/numeric comparisons (==, !=, >, <, >=, <=).
    Rejects function calls, attribute access, and arbitrary code.

    Args:
        expression: A simple condition expression
                    (e.g., "True", '"dev" == "prod"', "5 > 3")

    Returns:
        Boolean result of the evaluation.

    Raises:
        ValueError: If the expression is empty or contains unsupported constructs.

    """
    expression = expression.strip()
    if not expression:
        msg = "Empty condition expression"
        raise ValueError(msg)

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        msg = f"Invalid condition expression: {expression}"
        raise ValueError(msg) from exc

    return bool(_safe_eval_node(tree.body))


class ExpressionResolver:
    """Resolves ${...} expressions in workflow definitions.

    Supports:
    - ${input.field_name} - workflow inputs
    - ${variables.var_name} - workflow variables
    - ${activity_id.field} - activity outputs (direct field access)
    - ${activity_id.output.field} - activity outputs (via output key)
    - ${iteration_index} - loop iteration index
    - ${item} - forEach current item
    """

    def __init__(self) -> None:
        """Initialize expression resolver."""

    def resolve_expression(self, expression: object, workflow_state: dict[str, Any]) -> object:
        """Resolve ${...} expressions in a value.

        Type preservation: when the expression is a single template that spans
        the entire string (e.g. ``"${count}"``), the resolved value's original
        type is preserved (int, dict, list, etc.).  When multiple templates
        appear in the same string (e.g. ``"Count is ${count}"``), each resolved
        value is coerced to ``str`` so the result is always a string.

        Args:
            expression: Expression to resolve
            workflow_state: Current workflow state

        Returns:
            Resolved value

        """
        if not isinstance(expression, str):
            return expression

        # If no ${...} pattern, return as-is
        if "${" not in expression:
            return expression

        # Extract expression content
        pattern = r"\$\{([^}]+)\}"
        matches = re.findall(pattern, expression)

        if not matches:
            return expression

        # For single expression that matches entire string, return resolved value directly
        if len(matches) == 1 and expression == f"${{{matches[0]}}}":
            return self._resolve_single_expression(matches[0], workflow_state)

        # Multiple expressions - replace each in string
        result = expression
        for expr in matches:
            resolved = self._resolve_single_expression(expr, workflow_state)
            result = result.replace(f"${{{expr}}}", str(resolved))

        return result

    def evaluate_condition(self, condition: str, workflow_state: dict[str, Any]) -> bool:
        """Evaluate a conditional expression.

        Supports simple comparisons:
        - ${activity.output.field} == "value"
        - ${activity.output.status} != 0
        - ${activity.output.count} > 5

        Args:
            condition: Condition expression
            workflow_state: Current workflow state

        Returns:
            True if condition evaluates to true

        """
        # Resolve any ${...} expressions first
        resolved_condition = self.resolve_expression(condition, workflow_state)

        # If condition is already a boolean, return it
        if isinstance(resolved_condition, bool):
            return resolved_condition

        # Simple string-based evaluation for common patterns
        if isinstance(resolved_condition, str):
            # Handle comparison operators
            for op in SUPPORTED_OPERATORS:
                if op in resolved_condition:
                    parts = resolved_condition.split(op, 1)
                    if len(parts) != MIN_CONDITION_PARTS:
                        continue

                    left = parts[0].strip().strip("'\"")
                    right = parts[1].strip().strip("'\"")

                    # Validate operator is in supported set before casting
                    if op not in SUPPORTED_OPERATORS:
                        continue

                    # Cast op since we know it's from our literal list
                    typed_op = cast("ComparisonOp", op)

                    # Try numeric comparison first
                    try:
                        return self.evaluate_numeric_comparison(left, right, typed_op)
                    except ValueError:
                        # Fall back to string comparison
                        result = self.evaluate_string_comparison(left, right, typed_op)
                        if result is not None:
                            return result

            # If no operators, treat as truthy check
            return bool(resolved_condition)

        # Default to truthy evaluation
        return bool(resolved_condition)

    def evaluate_numeric_comparison(self, left: str, right: str, op: ComparisonOp) -> bool:
        """Evaluate numeric comparison.

        Args:
            left: Left operand
            right: Right operand
            op: Comparison operator

        Returns:
            Result of numeric comparison

        """
        left_num = float(left)
        right_num = float(right)
        if op == "==":
            return left_num == right_num
        if op == "!=":
            return left_num != right_num
        if op == ">":
            return left_num > right_num
        if op == "<":
            return left_num < right_num
        if op == ">=":
            return left_num >= right_num
        return left_num <= right_num

    def evaluate_string_comparison(self, left: str, right: str, op: ComparisonOp) -> bool | None:
        """Evaluate string comparison.

        Args:
            left: Left operand
            right: Right operand
            op: Comparison operator

        Returns:
            Result of string comparison or None if operator not supported

        """
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        return None

    def _resolve_single_expression(self, expr: str, workflow_state: dict[str, Any]) -> object:
        """Resolve a single expression path.

        Args:
            expr: Expression path (e.g., "input.field" or "activity.output.field")
            workflow_state: Current workflow state

        Returns:
            Resolved value

        Raises:
            KeyError: If the expression references an unknown scope or activity

        """
        parts = expr.split(".")

        # Handle input references (both singular "input" and plural "inputs")
        if parts[0] in ("input", "inputs"):
            return self._resolve_input_reference(parts, workflow_state)

        # Handle variable references
        if parts[0] == "variables":
            return self._resolve_variable_reference(parts, workflow_state)

        # Handle special loop variables
        if expr in workflow_state:
            return workflow_state[expr]

        # Handle activity output references
        if parts[0] in workflow_state.get("activity_outputs", {}):
            return self._resolve_activity_output(parts, workflow_state)

        msg = f"Expression '${{{expr}}}' references unknown activity or scope '{parts[0]}'"
        raise KeyError(msg)

    def _navigate_nested_path(self, value: object, parts: list[str]) -> object:
        """Navigate through nested dict/list structure.

        Args:
            value: Starting value
            parts: List of path parts to navigate

        Returns:
            Value at nested path or None

        """
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list) and part.isdigit():
                value = value[int(part)]
            else:
                return None
        return value

    def _resolve_input_reference(self, parts: list[str], workflow_state: dict[str, Any]) -> object:
        """Resolve input reference expression.

        Args:
            parts: Expression parts (e.g., ['input', 'field_name'])
            workflow_state: Current workflow state

        Returns:
            Resolved input value or default

        """
        value = workflow_state.get("inputs", {})
        return self._navigate_nested_path(value, parts[1:])

    def _resolve_variable_reference(self, parts: list[str], workflow_state: dict[str, Any]) -> object:
        """Resolve variable reference expression.

        Args:
            parts: Expression parts (e.g., ['variables', 'var_name'])
            workflow_state: Current workflow state

        Returns:
            Resolved variable value

        """
        value = workflow_state.get("variables", {})
        return self._navigate_nested_path(value, parts[1:])

    def _resolve_activity_output(self, parts: list[str], workflow_state: dict[str, Any]) -> object:
        """Resolve activity output reference.

        Args:
            parts: Expression parts (e.g., ['activity_id', 'output', 'field'])
            workflow_state: Current workflow state

        Returns:
            Resolved activity output value

        """
        activity_id = parts[0]
        value = workflow_state["activity_outputs"][activity_id]
        return self._navigate_nested_path(value, parts[1:])
