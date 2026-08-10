"""Verify all @fastapi_exception-decorated exceptions are registered on the app.

Regression test: ensure all the exception handlers are registered.
"""

import ast
from pathlib import Path

from syntara.core.exception_registry import _exception_registry


def _find_decorated_modules() -> set[str]:
    """Find all source modules that use @fastapi_exception as a class decorator."""
    src = Path(__file__).resolve().parents[3] / "src" / "syntara"
    modules = set()
    for py_file in src.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(), filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for dec in node.decorator_list:
                fn = dec.func if isinstance(dec, ast.Call) else dec
                if isinstance(fn, ast.Name) and fn.id == "fastapi_exception":
                    rel = py_file.relative_to(src.parent)
                    modules.add(str(rel).replace("/", ".").removesuffix(".py"))
                    break
            else:
                continue
            break
    return modules


def test_all_exception_modules_populate_registry() -> None:
    """Every module with @fastapi_exception must be imported by main.py."""
    # Importing main triggers all the side-effect imports
    import syntara.api.main  # noqa: F401

    decorated_modules = _find_decorated_modules()
    registered_module_names = {cls.__module__ for cls in _exception_registry}

    missing = decorated_modules - registered_module_names
    assert not missing, (
        f"Exception modules with @fastapi_exception not imported in main.py (handlers won't be registered): {missing}"
    )
