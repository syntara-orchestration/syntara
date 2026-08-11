"""Tests for workflow_context namespace resolution.

The workflow_context namespace is a reserved namespace (per handbook proposal P3)
that provides workflow metadata, execution metadata, and time context to expressions.

"now" and "today" are resolved dynamically per-node by the workflow engine
(not stored as static values in the metadata dict). Users who need the execution
start time should use ${workflow_context.execution.created_at}.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from syntara.workflows.utils.namespace_resolver import NamespaceResolver

SAMPLE_WORKFLOW_CONTEXT: dict[str, Any] = {
    "workflow": {
        "name": "My Test Workflow",
        "id": "abc-123-def-456",
        "version": 3,
        "published": True,
        "author": "Jane Doe",
    },
    "execution": {
        "id": "exec-789",
        "mode": "standard",
        "created_by": "John Smith",
        "created_at": "2024-01-15T10:30:00+00:00",
        "workflow_version_id": "ver-001",
    },
}


class TestWorkflowContextResolution:
    """Test that workflow_context namespace fields resolve correctly."""

    def _setup_resolver(self) -> NamespaceResolver:
        resolver = NamespaceResolver()
        resolver.set_namespace("workflow_context", SAMPLE_WORKFLOW_CONTEXT)
        return resolver

    def test_workflow_name(self) -> None:
        resolver = self._setup_resolver()
        assert resolver.resolve_value("${workflow_context.workflow.name}") == "My Test Workflow"

    def test_workflow_id(self) -> None:
        resolver = self._setup_resolver()
        assert resolver.resolve_value("${workflow_context.workflow.id}") == "abc-123-def-456"

    def test_workflow_version(self) -> None:
        resolver = self._setup_resolver()
        assert resolver.resolve_value("${workflow_context.workflow.version}") == 3

    def test_workflow_published(self) -> None:
        resolver = self._setup_resolver()
        assert resolver.resolve_value("${workflow_context.workflow.published}") is True

    def test_workflow_author(self) -> None:
        resolver = self._setup_resolver()
        assert resolver.resolve_value("${workflow_context.workflow.author}") == "Jane Doe"

    def test_execution_id(self) -> None:
        resolver = self._setup_resolver()
        assert resolver.resolve_value("${workflow_context.execution.id}") == "exec-789"

    def test_execution_mode(self) -> None:
        resolver = self._setup_resolver()
        assert resolver.resolve_value("${workflow_context.execution.mode}") == "standard"

    def test_execution_created_by(self) -> None:
        resolver = self._setup_resolver()
        assert resolver.resolve_value("${workflow_context.execution.created_by}") == "John Smith"

    def test_execution_created_at(self) -> None:
        resolver = self._setup_resolver()
        assert resolver.resolve_value("${workflow_context.execution.created_at}") == "2024-01-15T10:30:00+00:00"

    def test_execution_workflow_version_id(self) -> None:
        resolver = self._setup_resolver()
        assert resolver.resolve_value("${workflow_context.execution.workflow_version_id}") == "ver-001"

    def test_now_resolved_dynamically(self) -> None:
        """Verify now is resolved dynamically when set on the namespace dict."""
        resolver = self._setup_resolver()
        wf_ctx = resolver.get_namespace("workflow_context")
        current_time = datetime.now(UTC)
        wf_ctx["now"] = current_time.isoformat()
        result = resolver.resolve_value("${workflow_context.now}")
        assert result == current_time.isoformat()

    def test_today_resolved_dynamically(self) -> None:
        """Verify today is resolved dynamically when set on the namespace dict."""
        resolver = self._setup_resolver()
        wf_ctx = resolver.get_namespace("workflow_context")
        current_time = datetime.now(UTC)
        wf_ctx["today"] = current_time.strftime("%Y-%m-%d")
        result = resolver.resolve_value("${workflow_context.today}")
        assert result == current_time.strftime("%Y-%m-%d")

    def test_now_in_string_interpolation(self) -> None:
        resolver = self._setup_resolver()
        wf_ctx = resolver.get_namespace("workflow_context")
        wf_ctx["now"] = "2024-01-15T10:30:00+00:00"
        result = resolver.resolve_value("Started at ${workflow_context.now}")
        assert result == "Started at 2024-01-15T10:30:00+00:00"

    def test_string_interpolation(self) -> None:
        resolver = self._setup_resolver()
        result = resolver.resolve_value("Workflow ${workflow_context.workflow.name} is running")
        assert result == "Workflow My Test Workflow is running"

    def test_multiple_interpolations(self) -> None:
        resolver = self._setup_resolver()
        result = resolver.resolve_value("${workflow_context.workflow.name} v${workflow_context.workflow.version}")
        assert result == "My Test Workflow v3"

    def test_no_metadata_backward_compat(self) -> None:
        """Verify resolver works fine without workflow_context namespace."""
        resolver = NamespaceResolver()
        resolver.set_namespace("trigger", {"input": "value"})
        assert resolver.resolve_value("${trigger.input}") == "value"

    def test_metadata_does_not_collide_with_node_namespaces(self) -> None:
        """Verify workflow_context namespace doesn't interfere with node output namespaces."""
        resolver = self._setup_resolver()
        resolver.set_namespace("step_1", {"stdout": "hello"})
        assert resolver.resolve_value("${step_1.stdout}") == "hello"
        assert resolver.resolve_value("${workflow_context.workflow.name}") == "My Test Workflow"
