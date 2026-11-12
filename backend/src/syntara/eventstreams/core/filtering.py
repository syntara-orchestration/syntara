"""Prepare conservative early checks from the original native-compiled CEL AST."""

from typing import Any

from google.protobuf.message import DecodeError

from syntara.eventstreams.core.filter_input import EventFilterInput
from syntara.eventstreams.models.filter_configuration import FilterConfiguration
from syntara.filtering.ast import CheckedExpression
from syntara.filtering.evaluator import PreparedFilter
from syntara.filtering.models.result import FilterOutcome, FilterResult

_INDEX_ARGUMENT_COUNT = 2


def _key_header_only(node: dict[str, Any]) -> bool:  # noqa: PLR0911 - AST node-kind dispatch
    """Accept only subtrees whose input access is confined to key and headers.

    Bare input, computed root indexing and shadowing the input variable fall
    back to full evaluation. Comprehensions are inspected after native macro
    expansion; iterator variables are supplied by their checked ranges.
    """
    if "ident_expr" in node:
        return bool(node["ident_expr"]["name"].lstrip(".") != "input")
    if "select_expr" in node:
        select = node["select_expr"]
        operand = select["operand"]
        if operand.get("ident_expr", {}).get("name", "").lstrip(".") == "input":
            return select["field"] in {"key", "headers"}
        return _key_header_only(operand)
    if "call_expr" in node:
        call = node["call_expr"]
        args = call.get("args", [])
        if call["function"] == "_[_]" and args and args[0].get("ident_expr", {}).get("name", "").lstrip(".") == "input":
            return len(args) == _INDEX_ARGUMENT_COUNT and args[1].get("const_expr", {}).get("string_value") in {
                "key",
                "headers",
            }
        return ("target" not in call or _key_header_only(call["target"])) and all(_key_header_only(arg) for arg in args)
    if "comprehension_expr" in node:
        comprehension = node["comprehension_expr"]
        if any(comprehension.get(name) == "input" for name in ("iter_var", "iter_var2", "accu_var")):
            return False
        return all(
            _key_header_only(comprehension[name])
            for name in ("iter_range", "accu_init", "loop_condition", "loop_step", "result")
        )
    if "list_expr" in node:
        return all(_key_header_only(item) for item in node["list_expr"].get("elements", []))
    if "struct_expr" in node:
        return all(
            _key_header_only(entry["value"]) and ("map_key" not in entry or _key_header_only(entry["map_key"]))
            for entry in node["struct_expr"].get("entries", [])
        )
    return "const_expr" in node


def _conjuncts(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Inspect only mandatory AND operands; never pull conditions out of OR/NOT."""
    call = node.get("call_expr", {})
    if call.get("function") == "_&&_":
        return [part for arg in call["args"] for part in _conjuncts(arg)]
    return [node]


class PreparedSubscriptionFilter:
    """Keep the original expression and reuse native programs across messages."""

    __hash__ = None  # type: ignore[assignment]

    def __init__(self, configuration: FilterConfiguration) -> None:
        """Derive early checks from the checked AST without changing the full program."""
        self.expression = configuration.expression
        self._combined = configuration.prepared
        self._early: list[PreparedFilter] = []
        self._entirely_early = False
        serialized = self._combined.serialized
        if serialized is None:
            return
        try:
            checked = CheckedExpression(serialized)
            entirely_early = _key_header_only(checked.root)
            early = (
                []
                if entirely_early
                else [
                    PreparedFilter.from_serialized(checked.subtree(node))
                    for node in _conjuncts(checked.root)
                    if _key_header_only(node)
                ]
            )
        except (DecodeError, ValueError, KeyError, TypeError, RecursionError, RuntimeError):
            # Introspection is an optimization. Unsupported/deep native ASTs
            # retain their valid full program and require ordinary decoding.
            return
        self._entirely_early = entirely_early
        self._early = early

    def __eq__(self, other: object) -> bool:
        """Compare original source; prepared native programs are not configuration."""
        if not isinstance(other, PreparedSubscriptionFilter):
            return NotImplemented
        return self.expression == other.expression

    def precheck(self, value: EventFilterInput) -> FilterResult:
        """Only a proven rejection or a complete key/header-only result can finish early."""
        data = value.model_dump(mode="json", exclude_unset=True)
        if self._entirely_early:
            return self._combined.evaluate(data)
        if any(program.is_definitely_false(data) for program in self._early):
            return FilterResult(outcome=FilterOutcome.NO_MATCH)
        return FilterResult(outcome=FilterOutcome.MATCH)

    def evaluate(self, value: EventFilterInput) -> FilterResult:
        """Evaluate the original complete expression after payload validation."""
        return self._combined.evaluate(value.model_dump(mode="json", exclude_unset=True))
