"""CEL compatibility guards for strict predicates and safe regex diagnostics."""

from collections.abc import Iterable
from typing import cast

import re2  # type: ignore[import-untyped]  # google-re2 does not ship typing metadata.
from celpy import InterpretedRunner, celtypes
from celpy.evaluation import CELEvalError, CELFunction, Context, Evaluator, Result
from lark import Token, Tree

_COLLECTION_MACROS = frozenset({"all", "exists", "exists_one", "filter", "map"})
_BINARY_NODE_ARITY = 2
_TERNARY_NODE_ARITY = 3
_BINARY_OPERATIONS = {
    "addition_add": "_+_",
    "addition_sub": "_-_",
    "multiplication_mul": "_*_",
    "multiplication_div": "_/_",
    "multiplication_mod": "_%_",
    "relation_lt": "_<_",
    "relation_le": "_<=_",
    "relation_gt": "_>_",
    "relation_ge": "_>=_",
    "relation_eq": "_==_",
    "relation_ne": "_!=_",
    "relation_in": "_in_",
}


def _wrong_type() -> CELEvalError:
    return CELEvalError("no such overload", TypeError, ())


def is_missing_field_error(error: CELEvalError) -> bool:
    """Recognize only celpy's unresolved map-field and map-key errors."""
    message = error.args[0] if error.args and isinstance(error.args[0], str) else ""
    cause_type = error.args[1] if len(error.args) > 1 else None
    return cause_type is KeyError and (message == "no such key" or message.startswith("no such member in mapping:"))


def _predicate_error_priority(error: CELEvalError) -> int:
    """Keep wrong types and other failures from being hidden by missing fields."""
    cause_type = error.args[1] if len(error.args) > 1 else None
    if cause_type is TypeError or cause_type is AttributeError:
        return 2
    return 0 if is_missing_field_error(error) else 1


def _highest_priority_error(values: Iterable[Result]) -> CELEvalError | None:
    """Choose an unresolved error without depending on operand order."""
    return max(
        (value for value in values if isinstance(value, CELEvalError)),
        key=_predicate_error_priority,
        default=None,
    )


def _combine_predicates(operation: CELFunction, left: Result, right: Result) -> Result:
    """Keep unresolved errors until a decisive CEL boolean can resolve them."""
    left = left if isinstance(left, (celtypes.BoolType, CELEvalError)) else _wrong_type()
    right = right if isinstance(right, (celtypes.BoolType, CELEvalError)) else _wrong_type()
    if isinstance(left, CELEvalError) and isinstance(right, CELEvalError):
        return right if _predicate_error_priority(right) > _predicate_error_priority(left) else left
    return operation(left, right)


def safe_matches(text: Result, pattern: Result) -> celtypes.BoolType | CELEvalError:
    """Keep CEL's regex search behavior without logging the supplied pattern."""
    error = _highest_priority_error((text, pattern))
    if error is not None:
        return error
    if not isinstance(text, celtypes.StringType) or not isinstance(pattern, celtypes.StringType):
        return _wrong_type()
    options = re2.Options()
    options.log_errors = False
    try:
        return celtypes.BoolType(re2.search(pattern, text, options=options) is not None)
    except re2.error:
        return CELEvalError("filter_regex_error", ValueError, ())


class FilterEvaluator(Evaluator):
    """Preserve CEL errors instead of using Python truthiness for predicates."""

    def sub_evaluator(self, ast: Tree[Token]) -> "FilterEvaluator":
        """Retain compatibility guards and lexical scope inside nested macros."""
        return FilterEvaluator(ast, activation=self.activation)

    def _evaluate_binary(self, tree: Tree[Token]) -> Result:
        """Propagate operand errors before invoking CEL arithmetic or comparison."""
        operator_tree = cast("Tree[Token]", tree.children[0])
        (left, *_), right = cast("tuple[list[Result], Result]", self.visit_children(tree))
        error = _highest_priority_error((left, right))
        if error is not None:
            return error
        operation = self.activation.resolve_function(_BINARY_OPERATIONS[str(operator_tree.data)])
        try:
            return operation(left, right)
        except TypeError:
            return _wrong_type()
        except (ArithmeticError, ValueError) as failure:
            return CELEvalError("filter_operator_error", type(failure), ())

    def addition(self, tree: Tree[Token]) -> Result:
        """Keep missing operands symmetric for addition and subtraction."""
        if len(tree.children) != _BINARY_NODE_ARITY:
            return cast("Result", super().addition(tree))
        return self._evaluate_binary(tree)

    def multiplication(self, tree: Tree[Token]) -> Result:
        """Keep missing operands symmetric for multiplication, division and modulo."""
        if len(tree.children) != _BINARY_NODE_ARITY:
            return cast("Result", super().multiplication(tree))
        return self._evaluate_binary(tree)

    def relation(self, tree: Tree[Token]) -> Result:
        """Use the shared priority when both comparison operands have failed."""
        if len(tree.children) != _BINARY_NODE_ARITY:
            return cast("Result", super().relation(tree))
        return self._evaluate_binary(tree)

    def conditionaland(self, tree: Tree[Token]) -> Result:
        """Merge unresolved errors without losing CEL's decisive false result."""
        if len(tree.children) != _BINARY_NODE_ARITY:
            return cast("Result", super().conditionaland(tree))
        left, right = cast("tuple[Result, Result]", self.visit_children(tree))
        operation = self.activation.resolve_function("_&&_")
        try:
            return _combine_predicates(operation, left, right)
        except TypeError:
            return _wrong_type()

    def conditionalor(self, tree: Tree[Token]) -> Result:
        """Merge unresolved errors without losing CEL's decisive true result."""
        if len(tree.children) != _BINARY_NODE_ARITY:
            return cast("Result", super().conditionalor(tree))
        left, right = cast("tuple[Result, Result]", self.visit_children(tree))
        operation = self.activation.resolve_function("_||_")
        try:
            return _combine_predicates(operation, left, right)
        except TypeError:
            return _wrong_type()

    def expr(self, tree: Tree[Token]) -> Result:
        """Propagate a failed condition and evaluate only the chosen ternary branch."""
        if len(tree.children) != _TERNARY_NODE_ARITY:
            return cast("Result", super().expr(tree))
        condition = cast("Result", self.visit(cast("Tree[Token]", tree.children[0])))
        if isinstance(condition, CELEvalError):
            return condition
        if not isinstance(condition, celtypes.BoolType):
            return _wrong_type()
        branch = 1 if bool(condition) else 2
        return cast("Result", self.visit(cast("Tree[Token]", tree.children[branch])))

    def mapinits(self, tree: Tree[Token]) -> Result:
        """Preserve evaluation errors in map keys and values."""
        entries = self.visit_children(tree)
        error = _highest_priority_error(entries)
        result = celtypes.MapType()
        for key, value in zip(entries[::2], entries[1::2], strict=True):
            if isinstance(key, CELEvalError):
                continue
            if not celtypes.MapType.valid_key_type(key):
                error = _highest_priority_error((error, _wrong_type()))
                continue
            if key in result:
                duplicate = CELEvalError("filter_duplicate_map_key", ValueError, ())
                error = _highest_priority_error((error, duplicate))
                continue
            result[cast("celtypes.Value", key)] = (
                None if isinstance(value, CELEvalError) else cast("celtypes.Value", value)
            )
        return error if error is not None else result

    def member_index(self, tree: Tree[Token]) -> Result:
        """Preserve receiver/index errors before attempting a map or list lookup."""
        member, index = cast("tuple[Result, Result]", self.visit_children(tree))
        error = _highest_priority_error((member, index))
        if error is not None:
            return error
        operation = self.activation.resolve_function("_[_]")
        try:
            return operation(member, index)
        except TypeError:
            return _wrong_type()
        except KeyError:
            return CELEvalError("no such key", KeyError, ())
        except IndexError:
            return CELEvalError("invalid_argument", IndexError, ())

    def exprlist(self, tree: Tree[Token]) -> Result:
        """Preserve the strongest error in list literals and method arguments."""
        values = self.visit_children(tree)
        error = _highest_priority_error(values)
        if error is not None:
            return error
        return celtypes.ListType(cast("list[celtypes.Value]", values))

    def method_eval(
        self,
        object: Result,  # noqa: A002 - preserve celpy's keyword argument name.
        method_ident: Token,
        exprlist: Iterable[Result] | None = None,
    ) -> Result:
        """Merge receiver and argument errors before invoking an ordinary CEL method."""
        receiver = object
        arguments = [exprlist] if isinstance(exprlist, CELEvalError) else list(exprlist or ())
        error = _highest_priority_error((receiver, *arguments))
        if error is not None:
            return error
        return super().method_eval(receiver, method_ident, arguments)

    def macro_has_eval(self, exprlist: Tree[Token]) -> Result:  # type: ignore[override]  # CEL presence must preserve errors.
        """Treat missing fields as absent while retaining other evaluation failures."""
        value = self.visit_children(exprlist)[0]
        if isinstance(value, CELEvalError) and not is_missing_field_error(value):
            return value
        return celtypes.BoolType(not isinstance(value, CELEvalError))

    def member_dot_arg(self, tree: Tree[Token]) -> Result:
        """Return macro errors as values so outer CEL boolean logic can resolve them."""
        name = str(tree.children[1])
        if name not in _COLLECTION_MACROS:
            return cast("Result", super().member_dot_arg(tree))
        receiver = cast("Result", self.visit(cast("Tree[Token]", tree.children[0])))
        if isinstance(receiver, CELEvalError):
            return receiver
        if not isinstance(receiver, (celtypes.ListType, celtypes.MapType)):
            return _wrong_type()
        return self._evaluate_collection(tree, receiver, name)

    def _evaluate_logical_collection(
        self, tree: Tree[Token], receiver: celtypes.ListType | celtypes.MapType, name: str
    ) -> Result:
        """Fold all/exists predicates with CEL boolean resolution and ranked errors."""
        evaluate_body = self.build_ss_macro_eval(tree)
        logical = celtypes.logical_and if name == "all" else celtypes.logical_or
        accumulated: Result = celtypes.BoolType(name == "all")
        for item in receiver:
            value = cast("Result", evaluate_body(item))
            predicate = value if isinstance(value, (celtypes.BoolType, CELEvalError)) else _wrong_type()
            accumulated = _combine_predicates(logical, accumulated, predicate)
        return accumulated

    def _evaluate_collection(
        self, tree: Tree[Token], receiver: celtypes.ListType | celtypes.MapType, name: str
    ) -> Result:
        """Fold booleans with CEL operators and preserve errors in transformed values."""
        if name in {"all", "exists"}:
            return self._evaluate_logical_collection(tree, receiver, name)
        evaluate_body = self.build_ss_macro_eval(tree)
        selected: list[celtypes.Value] = []
        match_count = 0
        pending_error: CELEvalError | None = None
        for item in receiver:
            value = cast("Result", evaluate_body(item))
            if name != "map" and not isinstance(value, (celtypes.BoolType, CELEvalError)):
                value = _wrong_type()
            if isinstance(value, CELEvalError):
                pending_error = _highest_priority_error((pending_error, value))
                continue
            if name == "map":
                selected.append(cast("celtypes.Value", value))
                continue
            if bool(value):
                match_count += 1
                if name == "filter":
                    selected.append(item)
        if pending_error is not None:
            return pending_error
        if name == "exists_one":
            return celtypes.BoolType(match_count == 1)
        return celtypes.ListType(selected)


class FilterRunner(InterpretedRunner):
    """Use a fresh guarded evaluator for every activation of a prepared program."""

    def evaluate(self, context: Context) -> celtypes.Value:
        """Evaluate without reusing mutable per-message activation state."""
        evaluator = FilterEvaluator(ast=self.ast, activation=self.new_activation())
        return evaluator.evaluate(context)
