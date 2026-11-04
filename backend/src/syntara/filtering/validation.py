"""Validate the supported CEL surface without pretending to statically type check it."""

from lark import Token, Tree

from syntara.filtering.exceptions import FilterValidationCode, FilterValidationError

# Explicit names prevent a dependency update from silently exposing extensions.
_FUNCTION_ARITIES: dict[str, int] = {
    "bool": 1,
    "bytes": 1,
    "double": 1,
    "duration": 1,
    "int": 1,
    "size": 1,
    "string": 1,
    "timestamp": 1,
    "type": 1,
    "uint": 1,
}
_METHOD_ARITIES: dict[str, tuple[int, ...]] = {
    "contains": (1,),
    "endsWith": (1,),
    "getDate": (0, 1),
    "getDayOfMonth": (0, 1),
    "getDayOfWeek": (0, 1),
    "getDayOfYear": (0, 1),
    "getFullYear": (0, 1),
    "getHours": (0, 1),
    "getMilliseconds": (0, 1),
    "getMinutes": (0, 1),
    "getMonth": (0, 1),
    "getSeconds": (0, 1),
    "matches": (1,),
    "size": (0,),
    "startsWith": (1,),
}
_COLLECTION_MACROS = frozenset({"all", "exists", "exists_one", "filter", "map"})
_MEMBER_INDEX_ARITY = 2
_COLLECTION_MACRO_ARITY = 2
_EXPRESSION_WRAPPERS = frozenset(
    {"expr", "conditionalor", "conditionaland", "relation", "addition", "multiplication", "unary", "member", "primary"}
)


def _unwrap(node: Tree[Token]) -> Tree[Token]:
    """Strip parser wrappers without accepting an expression as a macro declaration."""
    while node.data in _EXPRESSION_WRAPPERS and len(node.children) == 1 and isinstance(node.children[0], Tree):
        node = node.children[0]
    return node


def _arguments(node: Tree[Token]) -> list[Tree[Token]]:
    """Read call arguments from celpy's unexpanded parse tree."""
    if isinstance(node.children[-1], Tree) and node.children[-1].data == "exprlist":
        return [child for child in node.children[-1].children if isinstance(child, Tree)]
    return []


def _is_presence_target(node: Tree[Token]) -> bool:
    """Allow named fields and literal string keys in presence checks."""
    target = _unwrap(node)
    if target.data == "member_dot":
        return True
    if target.data != "member_index" or len(target.children) != _MEMBER_INDEX_ARITY:
        return False
    index = target.children[1]
    if not isinstance(index, Tree):
        return False
    literal = _unwrap(index)
    return (
        literal.data == "literal"
        and len(literal.children) == 1
        and isinstance(literal.children[0], Token)
        and literal.children[0].type in {"STRING_LIT", "MLSTRING_LIT"}
    )


def _validate_macro(arguments: list[Tree[Token]], variables: frozenset[str]) -> None:
    """Bind one iteration variable only inside this collection macro's body."""
    if len(arguments) != _COLLECTION_MACRO_ARITY:
        raise FilterValidationError(FilterValidationCode.INVALID_MACRO)
    declaration = _unwrap(arguments[0])
    if declaration.data != "ident" or not isinstance(declaration.children[0], Token):
        raise FilterValidationError(FilterValidationCode.INVALID_MACRO)
    name = str(declaration.children[0])
    if name == "input":
        raise FilterValidationError(FilterValidationCode.INVALID_MACRO)
    _validate_node(arguments[1], variables | {name})


def _validate_function(name: str, arguments: list[Tree[Token]]) -> None:
    """Check global function names, argument counts and presence-check targets."""
    if name == "has":
        if len(arguments) != 1 or not _is_presence_target(arguments[0]):
            raise FilterValidationError(FilterValidationCode.INVALID_MACRO)
    elif name not in _FUNCTION_ARITIES:
        raise FilterValidationError(FilterValidationCode.UNSUPPORTED_FUNCTION)
    elif len(arguments) != _FUNCTION_ARITIES[name]:
        raise FilterValidationError(FilterValidationCode.INVALID_EXPRESSION)


def _validate_call(node: Tree[Token], variables: frozenset[str]) -> None:
    """Check calls explicitly; property names remain ordinary map fields."""
    arguments = _arguments(node)
    if node.data == "member_dot_arg":
        receiver, name_token = node.children[:2]
        if not isinstance(receiver, Tree):
            raise FilterValidationError(FilterValidationCode.INVALID_EXPRESSION)
        _validate_node(receiver, variables)
        name = str(name_token)
        if name in _COLLECTION_MACROS:
            _validate_macro(arguments, variables)
            return
        arities = _METHOD_ARITIES.get(name)
        if arities is None:
            raise FilterValidationError(FilterValidationCode.UNSUPPORTED_FUNCTION)
        if len(arguments) not in arities:
            raise FilterValidationError(FilterValidationCode.INVALID_EXPRESSION)
    else:
        _validate_function(str(node.children[0]), arguments)
    for argument in arguments:
        _validate_node(argument, variables)


def _validate_node(node: Tree[Token], variables: frozenset[str]) -> None:
    """Walk lexical scopes rather than collecting identifiers globally."""
    if node.data in {"member_object", "dot_ident_arg"}:
        raise FilterValidationError(FilterValidationCode.UNSUPPORTED_CONSTRUCT)
    if node.data in {"ident", "dot_ident"}:
        permitted = frozenset({"input"}) if node.data == "dot_ident" else variables
        if str(node.children[0]) not in permitted:
            raise FilterValidationError(FilterValidationCode.UNSUPPORTED_VARIABLE)
        return
    if node.data in {"ident_arg", "member_dot_arg"}:
        _validate_call(node, variables)
        return
    for child in node.children:
        if isinstance(child, Tree):
            _validate_node(child, variables)


def validate_expression_tree(expression: Tree[Token]) -> None:
    """Reject unsupported names and constructs, leaving message types to CEL."""
    _validate_node(expression, frozenset({"input"}))
