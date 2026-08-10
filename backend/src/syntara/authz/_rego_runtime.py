"""Minimal runtime for the regopy interpreter.

regopy's C extension leaks native memory (~6 MB per ``set_input``/``query``
cycle) when the process has imported heavy packages such as the full nexus
application.  The leak is in the native layer and cannot be fixed from
Python.  To bound total memory growth, the interpreter is automatically
recycled after a configurable number of evaluations.
"""

from __future__ import annotations

import json
from typing import Any

import regopy  # type: ignore[import-untyped]

_INTERPRETER: regopy.Interpreter | None = None
_POLICY_NAME: str = ""
_POLICY_TEXT: str = ""
_DECISION_QUERY = "data.nexus.authz"

_EVAL_COUNT: int = 0
_RECYCLE_EVERY: int = 32


def init(policy_name: str, policy_text: str, *, recycle_every: int = 32) -> None:
    """Create and store the interpreter with the given policy."""
    global _INTERPRETER, _POLICY_NAME, _POLICY_TEXT, _EVAL_COUNT, _RECYCLE_EVERY  # noqa: PLW0603
    _POLICY_NAME = policy_name
    _POLICY_TEXT = policy_text
    _RECYCLE_EVERY = recycle_every
    _EVAL_COUNT = 0
    interp = regopy.Interpreter()
    interp.add_module(policy_name, policy_text)
    _INTERPRETER = interp


def _recycle() -> regopy.Interpreter:
    """Replace the interpreter to release accumulated native memory."""
    import gc  # noqa: PLC0415

    global _INTERPRETER, _EVAL_COUNT  # noqa: PLW0603
    _EVAL_COUNT = 0
    _INTERPRETER = None
    gc.collect()
    interp = regopy.Interpreter()
    interp.add_module(_POLICY_NAME, _POLICY_TEXT)
    _INTERPRETER = interp
    return interp


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
    global _EVAL_COUNT  # noqa: PLW0603
    interp = _INTERPRETER
    if interp is None:
        msg = "regopy runtime not initialised — call init() first"
        raise RuntimeError(msg)
    _EVAL_COUNT += 1
    if _EVAL_COUNT >= _RECYCLE_EVERY:
        interp = _recycle()
    interp.set_input(regopy.Input(authz_input))
    return _query_to_dict(interp)


def evaluate_once(policy_name: str, policy_text: str, authz_input: dict[str, Any]) -> dict[str, Any]:
    """Create a temporary interpreter, evaluate, and discard it."""
    interp = regopy.Interpreter()
    interp.add_module(policy_name, policy_text)
    interp.set_input(regopy.Input(authz_input))
    return _query_to_dict(interp)
