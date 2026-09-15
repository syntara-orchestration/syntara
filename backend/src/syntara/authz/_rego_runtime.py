"""Minimal runtime for the regopy interpreter.

regopy's native library (``librego_shared.so``) statically links snmalloc and
exports ``operator new``/``operator delete``.  If another native library
(greenlet, temporalio's Rust bridge) is loaded first, libstdc++ allocation
symbols bind across two allocators and every ``query()`` call permanently
leaks ~69 KB of native memory.  The fix is import order, applied in
``syntara/__init__.py``: regopy is imported before anything else, which makes
the allocator bindings consistent and reduces the leak to ~0.1 KB per
evaluation.  See ``docs/standards/imports-and-modules.md`` ("Native import
order: regopy loads first").

Because the leak is prevented at load time, this runtime keeps a single
long-lived interpreter.  (An earlier revision recycled the interpreter every
N evaluations to "bound" the leak; measurements showed recycling had no
effect on the leak rate at any interval and only added re-parse latency, so
it was removed.)
"""

from __future__ import annotations

import json
from typing import Any

import regopy  # type: ignore[import-untyped]

_INTERPRETER: regopy.Interpreter | None = None
_DECISION_QUERY = "data.orchestrator.authz"


def init(policy_name: str, policy_text: str) -> None:
    """Create and store the interpreter with the given policy."""
    global _INTERPRETER  # noqa: PLW0603
    interp = regopy.Interpreter()
    interp.add_module(policy_name, policy_text)
    _INTERPRETER = interp


def shutdown() -> None:
    """Release the interpreter."""
    global _INTERPRETER  # noqa: PLW0603
    _INTERPRETER = None


def is_ready() -> bool:
    """Return whether the interpreter is initialised."""
    return _INTERPRETER is not None


def _query_to_dict(interp: regopy.Interpreter) -> dict[str, Any]:
    """Run the decision query and parse the first expression as JSON."""
    output = interp.query(_DECISION_QUERY)
    first_expr: Any = output.expressions()[0]
    raw: dict[str, Any] = json.loads(first_expr.json())
    return raw


def evaluate(authz_input: dict[str, Any]) -> dict[str, Any]:
    """Evaluate *authz_input* and return the normalised result dict."""
    interp = _INTERPRETER
    if interp is None:
        msg = "regopy runtime not initialised — call init() first"
        raise RuntimeError(msg)
    interp.set_input(regopy.Input(authz_input))
    return _query_to_dict(interp)


def evaluate_once(policy_name: str, policy_text: str, authz_input: dict[str, Any]) -> dict[str, Any]:
    """Create a temporary interpreter, evaluate, and discard it."""
    interp = regopy.Interpreter()
    interp.add_module(policy_name, policy_text)
    interp.set_input(regopy.Input(authz_input))
    return _query_to_dict(interp)
