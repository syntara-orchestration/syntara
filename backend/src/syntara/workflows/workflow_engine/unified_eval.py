"""Unified context-aware expression evaluator for workflow conditions.

Single evaluator for ALL boolean condition evaluation:
- Condition nodes
- Loop do_while conditions

Uses AST evaluation with direct namespace lookup instead of string substitution.

Security:
- Variable values are looked up from namespace (no repr() or string conversion)
- Visual-builder word operators are rewritten to Python before AST parsing
- Expression syntax is pre-processed to strip ${} wrappers before AST parsing
- No eval() or exec() - only AST-based evaluation with allowlist of node types
- ``ast.Call`` is allowed only for ``len``, ``str.startswith``/``endswith``,
  and internal ``__exists__`` / ``__is_empty__`` / ``__re_search__`` helpers
- AST complexity limits prevent denial-of-service attacks

Type Safety: Values used with original types (no repr() conversion)
"""

import ast
import json
import re
import subprocess
import sys
from typing import Any, Literal

from syntara.workflows.json_schema_validation import has_dangerous_pattern
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
MAX_REGEX_PATTERN_LENGTH = 500  # Max characters in a ``matches`` regex
MAX_REGEX_SUBJECT_LENGTH = 10_000  # Max characters in the ``matches`` subject string
REGEX_MATCH_TIMEOUT_SECONDS = 1.0  # Wall-clock cap around ``re.search`` (subprocess)
ERROR_PATTERN_DISPLAY_LENGTH = 80  # Truncate user regex patterns in error messages
_REGEX_WORKER_INVALID_EXIT = 2
# Isolated interpreter (``-S``) so startup stays well under the timeout.
# Pattern and subject travel on stdin JSON — never on argv — to avoid injection.
_REGEX_SEARCH_WORKER = """\
import json, re, sys
payload = json.load(sys.stdin)
try:
    found = re.search(payload["pattern"], payload["value"]) is not None
except re.error:
    sys.stdout.write(json.dumps({"error": "invalid"}))
    raise SystemExit(2)
sys.stdout.write(json.dumps({"found": found}))
"""
_EMPTYABLE_TYPES = (str, list, dict)
_EXISTS_PATH_NODE_TYPES = (ast.Constant, ast.Name, ast.Attribute, ast.Subscript, ast.UnaryOp)
_MIN_QUOTED_LITERAL_LENGTH = 2

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
    ast.Call,
)

# Gated Call allowlist — never look these names up in the user namespace
_ALLOWED_CALL_NAMES = frozenset({"len", "__exists__", "__is_empty__", "__re_search__"})
_ALLOWED_METHODS = frozenset({"startswith", "endswith"})

# Visual-builder operands: ${path} or a dotted/subscripted name
_OPERAND_PATTERN = r"(?:\$\{[^}]+\}|[A-Za-z_][\w.]*(?:\[[^\]]+\])*)"
_VALUE_PATTERN = r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|\d+(?:\.\d+)?|True|False|\$\{[^}]+\})"


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


def _operand_to_path(operand: str) -> str:
    """Extract the namespace path from a ``${path}`` operand or a bare name."""
    if operand.startswith("${") and operand.endswith("}"):
        return operand[2:-1]
    return operand


def _exists_repl(match: re.Match[str]) -> str:
    """Rewrite ``${x} exists`` to ``__exists__('x')`` so missing paths are False, not KeyError."""
    path = _operand_to_path(match.group(1))
    escaped = path.replace("\\", "\\\\").replace("'", "\\'")
    return f"__exists__('{escaped}')"


# Matches single- or double-quoted strings including escape sequences.
# Used as the leading alternative in quote-aware operator substitutions so that
# operator keywords inside string literals are never rewritten.
_QUOTED_SPAN = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''


def _translate_custom_operators(expression: str) -> str:
    """Rewrite visual-builder word operators to Python the AST evaluator can parse.

    The serializer already converts ``contains`` to ``in`` when saving, but the
    remaining operators are stored verbatim (``exists``, ``isEmpty``,
    ``startsWith``, …) and are not valid Python.  Already-published workflows
    keep those strings, so translation happens at evaluation time.

    The substitution is quote-aware: each regex alternates over a capturing
    quoted-span group (returned unchanged) and the actual operator pattern
    (rewritten).  This prevents a keyword that appears inside a string literal —
    for example, ``"Resource already exists in target"`` in a plain equality
    check — from being rewritten into a function call and corrupting a
    previously-valid comparison.
    """

    def _qa_sub(pat: str, repl: str, s: str) -> str:
        """Apply re.sub(pat, repl, s) while skipping occurrences inside quoted spans.

        Combines the quoted-span pattern with ``pat`` in an alternation so that
        a quoted span is consumed (and returned unchanged) before the operator
        pattern is attempted.  All backreferences in ``repl`` are shifted by +1
        to account for the quoted-span capture group inserted at position 1.
        """
        combined = rf"({_QUOTED_SPAN})|{pat}"
        shifted = re.sub(r"\\(\d+)", lambda m: f"\\{int(m.group(1)) + 1}", repl)

        def _repl(m: re.Match[str]) -> str:
            return m.group(0) if m.group(1) is not None else m.expand(shifted)

        return re.sub(combined, _repl, s)

    def _exists_repl_qa(m: re.Match[str]) -> str:
        r"""Quote-aware variant of _exists_repl.

        In the combined pattern ``({_QUOTED_SPAN})|({_OPERAND_PATTERN})\s+exists\b``
        the operand is captured in group 2 (not group 1) because the quoted-span
        group occupies position 1.
        """
        if m.group(1) is not None:
            return m.group(0)
        path = _operand_to_path(m.group(2))
        escaped = path.replace("\\", "\\\\").replace("'", "\\'")
        return f"__exists__('{escaped}')"

    replacements: tuple[tuple[str, str], ...] = (
        (rf"({_OPERAND_PATTERN})\s+lengthGreaterThan\s+({_VALUE_PATTERN})", r"(len(\1) > \2)"),
        (rf"({_OPERAND_PATTERN})\s+lengthLessThan\s+({_VALUE_PATTERN})", r"(len(\1) < \2)"),
        (rf"({_OPERAND_PATTERN})\s+lengthEqualTo\s+({_VALUE_PATTERN})", r"(len(\1) == \2)"),
        (rf"({_OPERAND_PATTERN})\s+startsWith\s+({_VALUE_PATTERN})", r"(\1.startswith(\2))"),
        (rf"({_OPERAND_PATTERN})\s+endsWith\s+({_VALUE_PATTERN})", r"(\1.endswith(\2))"),
        (rf"({_OPERAND_PATTERN})\s+contains\s+({_VALUE_PATTERN})", r"(\2 in \1)"),
        (rf"({_OPERAND_PATTERN})\s+isEmpty\b", r"(__is_empty__(\1))"),
    )
    translated = expression
    for pat, repl in replacements:
        translated = _qa_sub(pat, repl, translated)

    # ``matches`` requires a quoted string literal as the pattern. Templates
    # such as ``${trigger.regex}`` would otherwise become the regex itself,
    # letting webhook payloads supply untrusted patterns to ``re.search``.
    def _matches_repl_qa(m: re.Match[str]) -> str:
        if m.group(1) is not None:
            return m.group(0)
        operand = m.group(2)
        value = m.group(3)
        if not _is_quoted_string_literal(value):
            msg = "matches pattern must be a string literal"
            raise ValueError(msg)
        return f"(__re_search__({value}, {operand}))"

    matches_combined = rf"({_QUOTED_SPAN})|({_OPERAND_PATTERN})\s+matches\s+({_VALUE_PATTERN})"
    translated = re.sub(matches_combined, _matches_repl_qa, translated)

    # ``exists`` uses a callable replacement; wire it to the quote-aware variant
    # so the operand group index matches the combined pattern (group 2, not 1).
    exists_combined = rf"({_QUOTED_SPAN})|({_OPERAND_PATTERN})\s+exists\b"
    return re.sub(exists_combined, _exists_repl_qa, translated)


def _is_quoted_string_literal(value: str) -> bool:
    """Return True when ``value`` is a single- or double-quoted string token."""
    return len(value) >= _MIN_QUOTED_LITERAL_LENGTH and value[0] in {'"', "'"} and value[0] == value[-1]


def _path_exists(path: str, namespace: dict[str, Any]) -> bool:
    """Return True when ``path`` resolves in ``namespace`` to a non-None value.

    Uses the same Name / Attribute / Subscript lookup as condition evaluation
    (including ``data[0].name`` and ``items[-1]``). Missing keys or indexes are
    False, not a lookup error. Function calls in the path are rejected.
    """
    if not path:
        return False
    try:
        tree = ast.parse(path, mode="eval")
    except SyntaxError:
        return False
    _validate_ast_complexity(tree)
    try:
        value = _exists_resolve(tree.body, namespace)
    except (KeyError, IndexError):
        return False
    except TypeError as exc:
        if "exists does not support" in str(exc):
            raise
        return False
    return value is not None


def _lookup_attribute(base: object, attr: str) -> object:
    """Look up ``attr`` on a dict-like namespace value."""
    if not isinstance(base, dict):
        msg = f"Cannot access attribute '{attr}' on {type(base).__name__} (expected dict)"
        raise TypeError(msg)
    if attr not in base:
        msg = f"Attribute '{attr}' not found in {base.keys()}"
        raise KeyError(msg)
    return base[attr]


def _lookup_subscript(base: object, index: object) -> object:
    """Look up ``index`` on a dict or list namespace value."""
    if isinstance(base, dict):
        if index not in base:
            msg = f"Key {index!r} not found in dict"
            raise KeyError(msg)
        return base[index]

    if isinstance(base, list):
        if not isinstance(index, int):
            msg = f"List index must be integer, got {type(index).__name__}"
            raise TypeError(msg)
        if index < -len(base) or index >= len(base):
            msg = f"List index {index} out of range (length {len(base)})"
            raise IndexError(msg)
        return base[index]

    msg = f"Cannot subscript {type(base).__name__}"
    raise TypeError(msg)


def _negate_numeric(operand: object) -> object:
    """Apply unary minus to a numeric operand."""
    if not isinstance(operand, (int, float, complex)):
        msg = f"Unary minus requires numeric operand, got {type(operand).__name__}"
        raise TypeError(msg)
    return -operand


def _exists_resolve(node: ast.expr, namespace: dict[str, Any]) -> object:
    """Resolve an ``exists`` path without evaluating calls or comparisons."""
    if not isinstance(node, _EXISTS_PATH_NODE_TYPES):
        msg = f"exists does not support {type(node).__name__} paths"
        raise TypeError(msg)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return _eval_variable(node, namespace)
    if isinstance(node, ast.Attribute):
        return _lookup_attribute(_exists_resolve(node.value, namespace), node.attr)
    if isinstance(node, ast.Subscript):
        return _lookup_subscript(
            _exists_resolve(node.value, namespace),
            _exists_resolve(node.slice, namespace),
        )
    if not isinstance(node.op, ast.USub):
        msg = "exists does not support this unary operator in a path"
        raise TypeError(msg)
    return _negate_numeric(_exists_resolve(node.operand, namespace))


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

    expression = _translate_custom_operators(expression)

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
        msg = (
            f'The condition references "{node.id}" but no step with that name has produced '
            "output. Check that the step name is correct and runs before this condition."
        )
        raise KeyError(msg)
    return namespace[node.id]


def _eval_attribute(node: ast.Attribute, namespace: dict[str, Any]) -> Any:  # noqa: ANN401
    """Evaluate attribute access (e.g., user.role, fetch_order.riskScore)."""
    return _lookup_attribute(_eval_node(node.value, namespace), node.attr)


def _eval_subscript(node: ast.Subscript, namespace: dict[str, Any]) -> Any:  # noqa: ANN401
    """Evaluate subscript access (e.g., items[0], items[-1], data['key']).

    Supports Python-style negative indexing for lists (e.g., items[-1] for last element).
    """
    return _lookup_subscript(_eval_node(node.value, namespace), _eval_node(node.slice, namespace))


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
        return _negate_numeric(operand)

    msg = f"Unsupported unary operator: {type(node.op).__name__}"
    raise ValueError(msg)


def _eval_call(node: ast.Call, namespace: dict[str, Any]) -> object:
    """Evaluate a gated function/method call.

    Allowed: ``len(x)``, ``x.startswith(s)``, ``x.endswith(s)``,
    ``__exists__('path')``, ``__is_empty__(x)``, ``__re_search__(pattern, value)``.
    """
    if node.keywords or any(isinstance(arg, ast.Starred) for arg in node.args):
        msg = "Keyword and starred arguments are not supported"
        raise ValueError(msg)

    if isinstance(node.func, ast.Name):
        return _eval_allowed_function(node.func.id, node.args, namespace)

    if isinstance(node.func, ast.Attribute):
        return _eval_allowed_method(node.func, node.args, namespace)

    msg = f"Unsupported expression type: {type(node.func).__name__}"
    raise TypeError(msg)


def _eval_allowed_function(
    func_name: str,
    arg_nodes: list[ast.expr],
    namespace: dict[str, Any],
) -> object:
    """Evaluate an allowlisted bare function call."""
    if func_name not in _ALLOWED_CALL_NAMES:
        msg = f"Unsupported function: {func_name}"
        raise TypeError(msg)

    if func_name == "__re_search__":
        _require_literal_matches_pattern(arg_nodes)

    args = [_eval_node(arg, namespace) for arg in arg_nodes]
    if func_name == "len":
        return _eval_len(args)
    if func_name == "__exists__":
        return _eval_exists_call(args, namespace)
    if func_name == "__is_empty__":
        return _eval_is_empty(args)
    return _eval_re_search(args)


def _eval_len(args: list[object]) -> int:
    """Evaluate ``len(x)`` for strings and collections."""
    if len(args) != 1:
        msg = "len() takes exactly one argument"
        raise ValueError(msg)
    value = args[0]
    if not isinstance(value, (str, list, dict, tuple)):
        msg = f"len() not supported for {type(value).__name__}"
        raise TypeError(msg)
    return len(value)


def _eval_is_empty(args: list[object]) -> bool:
    """Evaluate ``isEmpty`` for strings and collections only — not Python truthiness."""
    if len(args) != 1:
        msg = "__is_empty__ takes exactly one argument"
        raise ValueError(msg)
    value = args[0]
    if not isinstance(value, _EMPTYABLE_TYPES):
        msg = f"isEmpty is not supported for {type(value).__name__}"
        raise TypeError(msg)
    return len(value) == 0


def _truncate_for_error(text: str) -> str:
    """Truncate a user-controlled string for log-safe error messages."""
    if len(text) <= ERROR_PATTERN_DISPLAY_LENGTH:
        return text
    return f"{text[:ERROR_PATTERN_DISPLAY_LENGTH]}..."


def _eval_exists_call(args: list[object], namespace: dict[str, Any]) -> bool:
    """Evaluate ``__exists__('path')``."""
    if len(args) != 1 or not isinstance(args[0], str):
        msg = "__exists__ requires a single string path"
        raise ValueError(msg)
    return _path_exists(args[0], namespace)


def _require_literal_matches_pattern(arg_nodes: list[ast.expr]) -> None:
    """Reject ``matches`` / ``__re_search__`` patterns that are not string constants.

    Translation already requires a quoted literal. This AST check also covers
    raw-mode ``__re_search__(namespace_value, subject)`` so a webhook field
    cannot become the regex.
    """
    if not arg_nodes:
        return
    pattern_node = arg_nodes[0]
    if not isinstance(pattern_node, ast.Constant) or not isinstance(pattern_node.value, str):
        msg = "matches pattern must be a string literal"
        raise ValueError(msg)  # noqa: TRY004 - provenance check, not a Python type mismatch


def _eval_re_search(args: list[object]) -> bool:
    """Evaluate ``__re_search__(pattern, value)`` for the ``matches`` operator."""
    expected_args = 2
    if len(args) != expected_args:
        msg = "__re_search__ takes exactly two arguments"
        raise ValueError(msg)
    pattern, value = args
    if not isinstance(pattern, str):
        msg = "matches pattern must be a string"
        raise TypeError(msg)
    if len(pattern) > MAX_REGEX_PATTERN_LENGTH:
        msg = f"matches pattern too long ({len(pattern)} chars, max {MAX_REGEX_PATTERN_LENGTH})"
        raise ValueError(msg)
    if not isinstance(value, str):
        msg = f"matches() requires a string value, got {type(value).__name__}"
        raise TypeError(msg)
    if len(value) > MAX_REGEX_SUBJECT_LENGTH:
        msg = f"matches subject too long ({len(value)} chars, max {MAX_REGEX_SUBJECT_LENGTH})"
        raise ValueError(msg)
    if has_dangerous_pattern(pattern):
        msg = (
            f"Potentially unsafe matches pattern: {_truncate_for_error(pattern)}. "
            "Nested quantifiers (e.g. '(a+)+') can cause catastrophic "
            "backtracking and are not allowed."
        )
        raise ValueError(msg)
    return _re_search_bounded(pattern, value)


def _re_search_bounded(pattern: str, value: str) -> bool:
    """Run ``re.search`` in a subprocess so catastrophic backtracking can be killed.

    CPython's regex engine is C code: a thread timeout cannot interrupt it.
    A child process can be killed when ``REGEX_MATCH_TIMEOUT_SECONDS`` elapses.
    """
    try:
        completed = subprocess.run(  # noqa: S603 - argv is a fixed interpreter + worker
            [sys.executable, "-S", "-c", _REGEX_SEARCH_WORKER],
            input=json.dumps({"pattern": pattern, "value": value}),
            capture_output=True,
            text=True,
            timeout=REGEX_MATCH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        msg = "matches timed out"
        raise ValueError(msg) from exc
    if completed.returncode == _REGEX_WORKER_INVALID_EXIT:
        msg = f"Invalid matches pattern: {_truncate_for_error(pattern)}"
        raise ValueError(msg)
    if completed.returncode != 0:
        msg = "matches failed"
        raise ValueError(msg)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        msg = "matches failed"
        raise ValueError(msg) from exc
    return bool(payload.get("found"))


def _eval_allowed_method(
    func: ast.Attribute,
    arg_nodes: list[ast.expr],
    namespace: dict[str, Any],
) -> bool:
    """Evaluate allowlisted string methods (startswith / endswith)."""
    method = func.attr
    if method not in _ALLOWED_METHODS:
        msg = f"Unsupported method: {method}"
        raise TypeError(msg)

    obj = _eval_node(func.value, namespace)
    args = [_eval_node(arg, namespace) for arg in arg_nodes]
    if len(args) != 1 or not isinstance(args[0], str):
        msg = f"{method}() requires a single string argument"
        raise TypeError(msg)
    if not isinstance(obj, str):
        msg = f"{method}() requires a string value, got {type(obj).__name__}"
        raise TypeError(msg)
    if method == "startswith":
        return obj.startswith(args[0])
    return obj.endswith(args[0])


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
    if isinstance(node, ast.Call):
        return _eval_call(node, namespace)

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
