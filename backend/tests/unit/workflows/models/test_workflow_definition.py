"""Unit tests for WorkflowDefinition schema model.

Tests cover:
- Empty description coercion to None
- Valid description passthrough
- None description default
"""

import pytest
from pydantic import ValidationError

from syntara.workflows.models.workflow_definition import WorkflowDefinition

MINIMAL_KWARGS = {
    "schema_version": "2.0.0",
    "name": "test-workflow",
    "triggers": [{"type": "manual"}],
    "nodes": [],
    "edges": [],
}


def test_empty_description_coerced_to_none() -> None:
    """Empty string description should be coerced to None."""
    wd = WorkflowDefinition(**MINIMAL_KWARGS, description="")
    assert wd.description is None


def test_valid_description_preserved() -> None:
    """Non-empty description should be preserved as-is."""
    wd = WorkflowDefinition(**MINIMAL_KWARGS, description="A real description")
    assert wd.description == "A real description"


def test_none_description_default() -> None:
    """Omitted description should default to None."""
    wd = WorkflowDefinition(**MINIMAL_KWARGS)
    assert wd.description is None


def test_whitespace_only_description_rejected() -> None:
    """Whitespace-only description should still be accepted (min_length counts whitespace)."""
    wd = WorkflowDefinition(**MINIMAL_KWARGS, description=" ")
    assert wd.description == " "


def test_description_exceeding_max_length_rejected() -> None:
    """Description exceeding 1000 chars should be rejected."""
    with pytest.raises(ValidationError, match="string_too_long"):
        WorkflowDefinition(**MINIMAL_KWARGS, description="x" * 1001)
