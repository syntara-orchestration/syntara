"""The workflow definition must not import activity modules.

Temporal runs workflow code in a sandbox that rejects the ``random`` access
structlog performs at import time. Any import chain from the workflow down into
``activities/`` therefore breaks worker validation and every integration test,
with a traceback that points at structlog rather than at the offending import.

These assertions are deliberately static. They run without a Temporal server,
so the boundary is checked on every unit run rather than only in CI's
much slower integration job.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

WORKFLOW_ENGINE = Path(__file__).resolve().parents[4] / "src/syntara/workflows/workflow_engine"

#: Modules that execute inside Temporal's workflow sandbox.
SANDBOXED_ROOTS = ("dynamic_workflow.py", "retry_mixin.py")


def _exempted_nodes(tree: ast.AST) -> set[int]:
    """Ids of nodes inside a ``workflow.unsafe.imports_passed_through()`` block.

    That context manager is Temporal's sanctioned escape hatch, so an activity
    import wrapped in it is deliberate rather than a mistake.
    """
    exempt: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.With) and "imports_passed_through" in ast.unparse(node.items[0]):
            for child in ast.walk(node):
                exempt.add(id(child))
    return exempt


def _imported_modules(path: Path) -> list[str]:
    """Every module named in an import that actually runs at workflow import time."""
    tree = ast.parse(path.read_text())
    exempt = _exempted_nodes(tree)
    names: list[str] = []
    for node in ast.walk(tree):
        if id(node) in exempt:
            continue
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


@pytest.mark.parametrize("filename", SANDBOXED_ROOTS)
def test_workflow_module_does_not_import_activities(filename: str) -> None:
    offenders = [m for m in _imported_modules(WORKFLOW_ENGINE / filename) if ".activities" in m]

    assert not offenders, (
        f"{filename} imports {offenders} from workflow code; that pulls structlog "
        "into Temporal's sandbox and fails worker validation. Move shared constants "
        "to a non-activity module (e.g. constants.py)."
    )


@pytest.mark.parametrize("filename", SANDBOXED_ROOTS)
def test_workflow_module_does_not_import_structlog(filename: str) -> None:
    offenders = [m for m in _imported_modules(WORKFLOW_ENGINE / filename) if "structlog" in m]

    assert not offenders, f"{filename} imports {offenders}; structlog is not sandbox-safe."
