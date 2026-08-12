"""Unified context-aware expression evaluator for workflow conditions.

Single evaluator for ALL boolean condition evaluation:
- Condition nodes
- Loop do_while conditions

Uses AST evaluation with direct namespace lookup instead of string substitution.

Security:
- Variable values are looked up from namespace (no repr() or string conversion)
- Expression syntax is pre-processed to strip ${} wrappers before AST parsing
- No eval() or exec() - only AST-based evaluation with allowlist of node types
- AST complexity limits prevent denial-of-service attacks

Type Safety: Values used with original types (no repr() conversion)
"""

import ast
import re
from typing import Any, Literal

from syntara.workflows.workflow_engine.expression_resolver import (
    _SAFE_COMPARISON_OPS,
    _compare,
)

ComparisonOp = Literal["==", "!=", ">=", "<=", ">", "<"]

# Security limits to prevent DoS attacks
MAX_EXPRESSION_LENGTH = 10_000  # Max characters in expression
MAX_VARIABLE_NAME_LENGTH = 500  # Max characters in ${variable.path.name}
MAX_AST_DEPTH = 50  # Max nesting depth (e.g., nested parentheses)
MAX_AST_NODES = 500  # Max total AST nodes

# Allowlist of safe AST node types — reject everything else up front
# Makes security contract self-documenting and ensures newly introduced AST types
# (e.g. ast.Lambda, ast.ListComp, ast.JoinedStr) are rejected without relying on fallthrough
_ALLOWED_NODE_TYPES = (
    ast.Constant,
    ast.Name,
    ast.Attribute,
    ast.Subscript,
    ast.Compare,
    ast.BoolOp,
    ast.UnaryOp,
)


def _validate_ast_complexity(tree: ast.AST) -> None:
    """Validate AST complexity to prevent DoS attacks.

    Raises:
        ValueError: If AST exceeds complexity limits

    """
    # Count total nodes
    node_count = sum(1 for _ in ast.walk(tree))
    if node_count > MAX_AST_NODES:
        msg = f"Expression too complex ({node_count} nodes, max {MAX_AST_NODES})"
        raise ValueError(msg)

    # Check maximum nesting depth
    def check_depth(node: ast.AST, current_depth: int) -> None:
        if current_depth > MAX_AST_DEPTH:
            msg = f"Expression too deeply nested (max depth {MAX_AST_DEPTH})"
            raise ValueError(msg)

        for child in ast.iter_child_nodes(node):
            check_depth(child, current_depth + 1)

    check_depth(tree, 0)


def safe_eval_with_namespace(expression: str, namespace: dict[str, Any]) -> bool:
    """Evaluate boolean expression with namespace context.

    Strips ${} wrappers and evaluates using AST with direct variable lookup.

    Security: Enforces limits on expression length, variable name length, AST depth,
    and total AST nodes to prevent denial-of-service attacks.

    Args:
        expression: Boolean expression like "${status} == 'completed'" or "status == 'completed'"
        namespace: All available data (node outputs, inputs, variables, loop context).
                   This is a defensive copy — modifications during evaluation do not
                   propagate back to the workflow state.

    Returns:
        Boolean evaluation result

    Raises:
        ValueError: Invalid expression syntax, unsupported construct, or complexity limit exceeded
        KeyError: Variable not found in namespace
        TypeError: Invalid type for operation (e.g., accessing attribute on non-dict)

    Examples:
        >>> namespace = {"status": "completed"}
        >>> safe_eval_with_namespace("${status} == 'completed'", namespace)
        True

        >>> namespace = {"fetch_order": {"riskScore": 0.8}}
        >>> safe_eval_with_namespace("${fetch_order.riskScore} > 0.7", namespace)
        True

        >>> namespace = {"loop": {"index": 5}}
        >>> safe_eval_with_namespace("${loop.index} < 10", namespace)
        True

    """
    if not expression or not expression.strip():
        msg = "Empty expression"
        raise ValueError(msg)

    # Enforce maximum expression length to prevent ReDoS
    if len(expression) > MAX_EXPRESSION_LENGTH:
        msg = f"Expression too long ({len(expression)} chars, max {MAX_EXPRESSION_LENGTH})"
        raise ValueError(msg)

    # Strip ${} wrappers - use simple non-backtracking pattern
    # Fast path: skip regex if no templates present
    if "${" not in expression:
        cleaned = expression
    else:
        # Non-greedy match prevents catastrophic backtracking
        # Validates variable name length separately to avoid ReDoS
        def replace_template(match: re.Match[str]) -> str:
            var_name = match.group(1)
            if len(var_name) > MAX_VARIABLE_NAME_LENGTH:
                msg = f"Variable name too long ({len(var_name)} chars, max {MAX_VARIABLE_NAME_LENGTH})"
                raise ValueError(msg)
            return var_name

        pattern = r"\$\{([^}]+?)\}"  # Non-greedy, simple pattern
        cleaned = re.sub(pattern, replace_template, expression)

    # Pre-parse validation: check nesting depth before AST parsing
    # Count dots as proxy for attribute access depth to prevent parser crashes
    max_dots = cleaned.count(".")
    if max_dots > MAX_AST_DEPTH:
        msg = f"Expression too deeply nested ({max_dots} levels, max {MAX_AST_DEPTH})"
        raise ValueError(msg)

    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as e:
        msg = f"Invalid expression syntax: {expression}"
        raise ValueError(msg) from e

    # Validate AST complexity after parsing (defense in depth)
    _validate_ast_complexity(tree)

    result = _eval_node(tree.body, namespace)
    return bool(result)


def _eval_variable(node: ast.Name, namespace: dict[str, Any]) -> Any:  # noqa: ANN401
    """Evaluate variable reference (e.g., status, user, fetch_order)."""
    if node.id not in namespace:
        msg = f"Variable '{node.id}' not found in namespace"
        raise KeyError(msg)
    return namespace[node.id]


def _eval_attribute(node: ast.Attribute, namespace: dict[str, Any]) -> Any:  # noqa: ANN401
    """Evaluate attribute access (e.g., user.role, fetch_order.riskScore)."""
    base = _eval_node(node.value, namespace)
    if not isinstance(base, dict):
        msg = f"Cannot access attribute '{node.attr}' on {type(base).__name__} (expected dict)"
        raise TypeError(msg)
    if node.attr not in base:
        msg = f"Attribute '{node.attr}' not found in {base.keys()}"
        raise KeyError(msg)
    return base[node.attr]


def _eval_subscript(node: ast.Subscript, namespace: dict[str, Any]) -> Any:  # noqa: ANN401
    """Evaluate subscript access (e.g., items[0], items[-1], data['key']).

    Supports Python-style negative indexing for lists (e.g., items[-1] for last element).
    """
    base = _eval_node(node.value, namespace)
    index = _eval_node(node.slice, namespace)

    if isinstance(base, dict):
        if index not in base:
            msg = f"Key {index!r} not found in dict"
            raise KeyError(msg)
        return base[index]

    if isinstance(base, list):
        if not isinstance(index, int):
            msg = f"List index must be integer, got {type(index).__name__}"
            raise TypeError(msg)
        # Allow negative indexing: -1 for last element, -2 for second-to-last, etc.
        # Validate bounds: index must be >= -len(base) and < len(base)
        if index < -len(base) or index >= len(base):
            msg = f"List index {index} out of range (length {len(base)})"
            raise IndexError(msg)
        return base[index]

    msg = f"Cannot subscript {type(base).__name__}"
    raise TypeError(msg)


def _eval_bool_op(node: ast.BoolOp, namespace: dict[str, Any]) -> bool:
    """Evaluate boolean operators (and, or) with short-circuit evaluation.

    Short-circuit: For 'and', stops at first falsy value. For 'or', stops at first truthy value.
    """
    if isinstance(node.op, ast.And):
        # Short-circuit: stop at first falsy value
        for value_node in node.values:
            result = _eval_node(value_node, namespace)
            if not result:
                return False
        return True

    if isinstance(node.op, ast.Or):
        # Short-circuit: stop at first truthy value
        for value_node in node.values:
            result = _eval_node(value_node, namespace)
            if result:
                return True
        return False

    msg = f"Unsupported boolean operator: {type(node.op).__name__}"
    raise ValueError(msg)


def _eval_unary_op(node: ast.UnaryOp, namespace: dict[str, Any]) -> object:
    """Evaluate unary operators (not, -)."""
    operand = _eval_node(node.operand, namespace)

    if isinstance(node.op, ast.Not):
        return not operand

    if isinstance(node.op, ast.USub):
        # Validate operand is numeric before negation
        if not isinstance(operand, (int, float, complex)):
            msg = f"Unary minus requires numeric operand, got {type(operand).__name__}"
            raise TypeError(msg)
        return -operand

    msg = f"Unsupported unary operator: {type(node.op).__name__}"
    raise ValueError(msg)


def _eval_node(node: ast.expr, namespace: dict[str, Any]) -> object:
    """Evaluate AST node with namespace context.

    Dispatches to specialized handler functions based on node type.

    Args:
        node: AST expression node to evaluate
        namespace: Variable namespace for lookups

    Returns:
        Evaluated value (can be any type)

    Raises:
        ValueError: Unsupported AST node type
        KeyError: Variable not found in namespace
        TypeError: Invalid type for operation

    """
    # Reject unsupported AST node types up front (security boundary)
    if not isinstance(node, _ALLOWED_NODE_TYPES):
        msg = (
            f"Unsupported expression type: {type(node).__name__}. "
            f"Only variables, comparisons, and boolean operators are supported."
        )
        raise TypeError(msg)

    # Constant values are returned directly
    if isinstance(node, ast.Constant):
        return node.value

    # Variable access handlers
    if isinstance(node, ast.Name):
        return _eval_variable(node, namespace)
    if isinstance(node, ast.Attribute):
        return _eval_attribute(node, namespace)
    if isinstance(node, ast.Subscript):
        return _eval_subscript(node, namespace)

    # Comparison and boolean operation handlers
    if isinstance(node, ast.Compare):
        return _eval_compare(node, namespace)
    if isinstance(node, ast.BoolOp):
        return _eval_bool_op(node, namespace)

    # UnaryOp guaranteed by allowlist above
    return _eval_unary_op(node, namespace)


def _eval_compare(node: ast.Compare, namespace: dict[str, Any]) -> bool:
    """Evaluate comparison chain.

    Supports: ==, !=, >, <, >=, <=, in, not in

    Args:
        node: AST Compare node
        namespace: Variable namespace

    Returns:
        Boolean result of comparison

    """
    left = _eval_node(node.left, namespace)

    for op, comparator in zip(node.ops, node.comparators, strict=True):
        # Handle 'in' and 'not in' operators (for Python backend)
        if isinstance(op, ast.In):
            right = _eval_node(comparator, namespace)
            if left not in right:  # type: ignore[operator]
                return False
            left = right
            continue
        if isinstance(op, ast.NotIn):
            right = _eval_node(comparator, namespace)
            if left in right:  # type: ignore[operator]
                return False
            left = right
            continue

        # Handle standard comparison operators
        if type(op) not in _SAFE_COMPARISON_OPS:
            msg = f"Unsupported operator: {type(op).__name__}"
            raise ValueError(msg)

        right = _eval_node(comparator, namespace)
        op_str: ComparisonOp = _SAFE_COMPARISON_OPS[type(op)]  # type: ignore[assignment]

        if not _compare(left, right, op_str):
            return False

        left = right

    return True
