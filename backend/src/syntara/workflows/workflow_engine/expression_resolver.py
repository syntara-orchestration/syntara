"""Safe AST evaluation for workflow condition expressions.

Live ``${...}`` template resolution uses ``NamespaceResolver``. This module only
provides ``safe_eval_condition`` and the comparison helpers imported by
``unified_eval.py``.
"""

import ast
from typing import Literal, cast

# Type alias for comparison operators
ComparisonOp = Literal["==", "!=", ">=", "<=", ">", "<"]

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
