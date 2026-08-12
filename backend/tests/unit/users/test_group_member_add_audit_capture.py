"""Regression: membership @audit decorators must be SECURITY_EVENT with user identity (AAP-83643)."""

import ast
from pathlib import Path


def _audit_call(func_node: ast.AsyncFunctionDef) -> ast.Call:
    for dec in func_node.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        func = dec.func
        if isinstance(func, ast.Name) and func.id == "audit":
            return dec
        if isinstance(func, ast.Attribute) and func.attr == "audit":
            return dec
    missing = f"{func_node.name} @audit decorator not found"
    raise AssertionError(missing)


def _event_category_name(call: ast.Call) -> str:
    # @audit(EventCategory.SECURITY_EVENT, event_action=..., ...)
    if call.args:
        node = call.args[0]
    else:
        kwargs = {kw.arg: kw.value for kw in call.keywords if kw.arg}
        node = kwargs["event_category"]
    assert isinstance(node, ast.Attribute)
    assert isinstance(node.value, ast.Name)
    assert node.value.id == "EventCategory"
    return node.attr


def _capture_args_values(call: ast.Call) -> set[str]:
    kwargs = {kw.arg: kw.value for kw in call.keywords if kw.arg}
    node = kwargs["capture_args"]
    assert isinstance(node, ast.Set), "capture_args should be a set literal"
    values: set[str] = set()
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            values.add(elt.value)
    return values


def test_group_member_add_audit_is_security_event_and_captures_request() -> None:
    """add_member must be SECURITY_EVENT and capture request (contains user_id)."""
    router_path = Path(__file__).resolve().parents[3] / "src/syntara/users/groups_router.py"
    tree = ast.parse(router_path.read_text())
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "add_member":
            call = _audit_call(node)
            assert _event_category_name(call) == "SECURITY_EVENT"
            captured = _capture_args_values(call)
            assert "group_id" in captured
            assert "request" in captured
            return
    missing = "add_member function not found in groups_router.py"
    raise AssertionError(missing)


def test_group_member_remove_audit_is_security_event() -> None:
    """remove_member must be SECURITY_EVENT (not USER_ACTION)."""
    router_path = Path(__file__).resolve().parents[3] / "src/syntara/users/groups_router.py"
    tree = ast.parse(router_path.read_text())
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "remove_member":
            call = _audit_call(node)
            assert _event_category_name(call) == "SECURITY_EVENT"
            captured = _capture_args_values(call)
            assert "user_id" in captured
            return
    missing = "remove_member function not found in groups_router.py"
    raise AssertionError(missing)


def test_user_groups_set_audit_is_security_event_and_captures_request() -> None:
    """set_user_groups must be SECURITY_EVENT and capture request body."""
    router_path = Path(__file__).resolve().parents[3] / "src/syntara/users/users_router.py"
    tree = ast.parse(router_path.read_text())
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "set_user_groups":
            call = _audit_call(node)
            assert _event_category_name(call) == "SECURITY_EVENT"
            captured = _capture_args_values(call)
            assert "user_id" in captured
            assert "request" in captured
            return
    missing = "set_user_groups function not found in users_router.py"
    raise AssertionError(missing)
