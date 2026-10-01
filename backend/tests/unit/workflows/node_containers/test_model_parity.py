"""Portable schemas must match the existing workflow parameter contracts."""

import importlib
from pathlib import Path

import pytest

from syntara.workflows.workflow_engine.models import workflow_definition


@pytest.mark.parametrize(
    "name",
    [
        "ScriptExecutorParameters",
        "APIExecutorParameters",
        "AgenticExecutorParameters",
        "AAPJobTemplateExecutorParameters",
        "AAPWorkflowJobTemplateExecutorParameters",
        "ScriptOutput",
        "HttpRequestOutput",
        "AAPJobTemplateOutput",
        "AAPWorkflowJobTemplateOutput",
    ],
)
def test_schema_parity(name, monkeypatch):
    backend = Path(__file__).resolve().parents[4]
    monkeypatch.syspath_prepend(str(backend / "nodes/_shared/src"))
    portable = importlib.import_module("syntara_node_runtime.models")
    actual = getattr(portable, name).model_json_schema()
    expected = getattr(workflow_definition, name).model_json_schema()
    assert actual == expected
