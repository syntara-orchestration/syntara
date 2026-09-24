"""Tests for the ``node_kind_disabled`` validation findings (ANSTRAT-1750, F-17).

The kill-switch setting is supplied by the caller, so these tests pass the
disabled set directly instead of mocking the settings cache.
"""

from __future__ import annotations

from typing import Any

from syntara.workflows.models.validation_finding import ValidationCategory, ValidationSeverity
from syntara.workflows.validators import workflow_validator
from syntara.workflows.validators.workflow_definition import disabled_kind_findings


def _definition(*nodes: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal but schema-valid V2 definition wired from a manual trigger."""
    return {
        "schema_version": "2.0.0",
        "name": "kill-switch-test",
        "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
        "nodes": list(nodes),
        "edges": [{"from": "t1", "to": node["id"]} for node in nodes],
    }


def _script_node(node_id: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "script",
        "parameters": {"language": "python", "code": "print(1)"},
    }


def _http_node(node_id: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "http_request",
        "parameters": {"url": "https://example.com", "method": "GET"},
    }


class TestDisabledKindFindings:
    """The standalone collector used by both the validator and the save paths."""

    def test_no_findings_when_nothing_is_disabled(self) -> None:
        assert disabled_kind_findings(_definition(_script_node("a")), frozenset()) == []

    def test_error_per_offending_node(self) -> None:
        findings = disabled_kind_findings(_definition(_script_node("a"), _script_node("b")), frozenset({"script"}))
        assert [f.node_id for f in findings] == ["a", "b"]
        assert all(f.severity is ValidationSeverity.error for f in findings)
        assert all(f.category is ValidationCategory.node_kind_disabled for f in findings)

    def test_message_names_the_node_and_the_kind(self) -> None:
        findings = disabled_kind_findings(_definition(_script_node("runner")), frozenset({"script"}))
        assert "runner" in findings[0].message
        assert "script" in findings[0].message

    def test_untouched_kinds_are_not_reported(self) -> None:
        findings = disabled_kind_findings(_definition(_http_node("a")), frozenset({"script"}))
        assert findings == []

    def test_warns_when_a_save_removes_the_disabled_nodes(self) -> None:
        """The lenient rule: removing the offending nodes is allowed, with a warning."""
        previous = _definition(_script_node("a"))
        current = _definition(_http_node("a"))
        findings = disabled_kind_findings(current, frozenset({"script"}), previous_definition=previous)
        assert len(findings) == 1
        assert findings[0].severity is ValidationSeverity.warning
        assert findings[0].category is ValidationCategory.node_kind_disabled
        assert "script" in findings[0].message
        assert findings[0].node_id is None

    def test_no_warning_when_the_previous_version_was_clean(self) -> None:
        previous = _definition(_http_node("a"))
        current = _definition(_http_node("a"))
        assert disabled_kind_findings(current, frozenset({"script"}), previous_definition=previous) == []

    def test_errors_win_over_the_removal_warning(self) -> None:
        """A definition that still contains a disabled node is an error, not a warning."""
        previous = _definition(_script_node("a"), _script_node("b"))
        current = _definition(_script_node("a"))
        findings = disabled_kind_findings(current, frozenset({"script"}), previous_definition=previous)
        assert [f.severity for f in findings] == [ValidationSeverity.error]


class TestValidatorIntegration:
    """``collect_findings`` surfaces the finding and blocks the save."""

    def test_definition_is_valid_when_the_kind_is_enabled(self) -> None:
        result = workflow_validator.collect_findings(_definition(_script_node("a")))
        assert result.is_valid is True

    def test_disabled_kind_makes_the_definition_invalid(self) -> None:
        result = workflow_validator.collect_findings(
            _definition(_script_node("a")),
            disabled_node_kinds=frozenset({"script"}),
        )
        assert result.is_valid is False
        categories = [f.category for f in result.findings]
        assert ValidationCategory.node_kind_disabled in categories

    def test_removal_warning_does_not_block_the_save(self) -> None:
        result = workflow_validator.collect_findings(
            _definition(_http_node("a")),
            disabled_node_kinds=frozenset({"script"}),
            previous_definition=_definition(_script_node("a")),
        )
        assert result.is_valid is True
        assert result.warning_count == 1
        assert result.findings[0].category is ValidationCategory.node_kind_disabled
