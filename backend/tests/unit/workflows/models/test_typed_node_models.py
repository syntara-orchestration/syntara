"""Unit tests for typed workflow node models and control node parameters.

Tests validation, discriminated union resolution, and model_dump behavior
for the WorkflowNode typed models introduced in AAP-77227.
"""

from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from syntara.workflows.models.workflow_definition import (
    WorkflowDefinition,
)
from syntara.workflows.workflow_engine.models.workflow_definition import (
    ApprovalNodeParameters,
    ConditionNodeParameters,
    ConvergeNodeParameters,
    DoWhileLoopParameters,
    ForEachLoopParameters,
    SwitchCase,
    SwitchNodeParameters,
    WaitNodeParameters,
)


class TestConditionNodeParameters:
    """Tests for ConditionNodeParameters validation."""

    def test_valid(self) -> None:
        p = ConditionNodeParameters(condition="1 == 1")
        assert p.condition == "1 == 1"

    def test_rejects_empty_condition(self) -> None:
        with pytest.raises(ValidationError):
            ConditionNodeParameters(condition="")


class TestSwitchNodeParameters:
    """Tests for SwitchNodeParameters validation."""

    def test_valid(self) -> None:
        p = SwitchNodeParameters(
            cases=[SwitchCase(port="c0", label="Case 0", condition="1 == 1")],
        )
        assert len(p.cases) == 1
        assert p.default_port is None

    def test_rejects_empty_cases(self) -> None:
        with pytest.raises(ValidationError):
            SwitchNodeParameters(cases=[])

    def test_case_rejects_empty_port(self) -> None:
        with pytest.raises(ValidationError):
            SwitchCase(port="", label="Label", condition="1 == 1")


class TestConvergeNodeParameters:
    """Tests for ConvergeNodeParameters validation."""

    def test_defaults(self) -> None:
        p = ConvergeNodeParameters()
        assert p.strategy is None
        assert p.n_required is None
        assert p.wait_duration is None

    def test_n_required_minimum(self) -> None:
        with pytest.raises(ValidationError):
            ConvergeNodeParameters(n_required=0)


class TestLoopParameters:
    """Tests for ForEachLoopParameters and DoWhileLoopParameters validation."""

    def test_for_each(self) -> None:
        p = ForEachLoopParameters(type="for_each", items="${trigger.list}")
        assert p.type == "for_each"
        assert p.items == "${trigger.list}"

    def test_do_while(self) -> None:
        p = DoWhileLoopParameters(type="do_while", condition="1 == 1")
        assert p.type == "do_while"

    def test_for_each_rejects_empty_items(self) -> None:
        with pytest.raises(ValidationError):
            ForEachLoopParameters(type="for_each", items="")


class TestWaitNodeParameters:
    """Tests for WaitNodeParameters validation."""

    def test_valid(self) -> None:
        p = WaitNodeParameters(duration=10)
        assert p.duration == 10

    def test_rejects_zero(self) -> None:
        with pytest.raises(ValidationError):
            WaitNodeParameters(duration=0)


class TestApprovalNodeParameters:
    """Tests for ApprovalNodeParameters validation."""

    def test_defaults(self) -> None:
        p = ApprovalNodeParameters()
        assert p.credential_id is None
        assert p.approver_users is None
        assert p.approver_groups is None
        assert p.prompt is None
        assert p.fallback_decision is None

    def test_with_approvers(self) -> None:
        p = ApprovalNodeParameters(
            approver_users=["admin"],
            approver_groups=["leads"],
            prompt="Please approve",
        )
        assert p.approver_users == ["admin"]
        assert p.approver_groups == ["leads"]

    def test_invalid_fallback_decision(self) -> None:
        with pytest.raises(ValidationError):
            ApprovalNodeParameters(fallback_decision="maybe")  # type: ignore[arg-type]


class TestWorkflowNodeDiscriminatedUnion:
    """Test that the discriminated union resolves to correct node types."""

    def _make_workflow(self, nodes: list[dict[str, Any]]) -> WorkflowDefinition:
        return WorkflowDefinition.model_validate(
            {
                "schema_version": "2.0.0",
                "name": "test",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": nodes,
                "edges": [{"from": "trigger", "to": nodes[0]["id"]}],
            }
        )

    def test_script_node(self) -> None:
        wf = self._make_workflow(
            [
                {"id": "n1", "type": "script", "parameters": {"language": "bash", "code": "echo hi"}},
            ]
        )
        assert type(wf.nodes[0]).__name__ == "ScriptNode"

    def test_switch_node(self) -> None:
        wf = self._make_workflow(
            [
                {
                    "id": "n1",
                    "type": "switch",
                    "parameters": {"cases": [{"port": "c0", "label": "C0", "condition": "1==1"}]},
                },
            ]
        )
        assert type(wf.nodes[0]).__name__ == "SwitchNode"

    def test_wait_node(self) -> None:
        wf = self._make_workflow(
            [
                {"id": "n1", "type": "wait", "parameters": {"duration": 5}},
            ]
        )
        assert type(wf.nodes[0]).__name__ == "WaitNode"

    def test_condition_node(self) -> None:
        wf = self._make_workflow(
            [
                {"id": "n1", "type": "condition", "parameters": {"condition": "1==1"}},
            ]
        )
        assert type(wf.nodes[0]).__name__ == "ConditionNode"

    def test_converge_node(self) -> None:
        wf = self._make_workflow(
            [
                {"id": "n1", "type": "converge", "parameters": {}},
            ]
        )
        assert type(wf.nodes[0]).__name__ == "ConvergeNode"

    def test_approval_node(self) -> None:
        wf = self._make_workflow(
            [
                {"id": "n1", "type": "approval", "parameters": {}},
            ]
        )
        assert type(wf.nodes[0]).__name__ == "ApprovalNode"

    def test_loop_for_each(self) -> None:
        wf = self._make_workflow(
            [
                {"id": "n1", "type": "loop", "parameters": {"type": "for_each", "items": "${trigger.list}"}},
            ]
        )
        assert type(wf.nodes[0]).__name__ == "LoopNode"

    def test_loop_do_while(self) -> None:
        wf = self._make_workflow(
            [
                {"id": "n1", "type": "loop", "parameters": {"type": "do_while", "condition": "1==1"}},
            ]
        )
        assert type(wf.nodes[0]).__name__ == "LoopNode"

    def test_http_request_node(self) -> None:
        wf = self._make_workflow(
            [
                {"id": "n1", "type": "http_request", "parameters": {"method": "GET", "url": "http://example.com"}},
            ]
        )
        assert type(wf.nodes[0]).__name__ == "HTTPRequestNode"

    def test_agentic_node(self) -> None:
        wf = self._make_workflow(
            [
                {"id": "n1", "type": "agentic", "parameters": {"prompt": "do something"}},
            ]
        )
        assert type(wf.nodes[0]).__name__ == "AgenticNode"

    def test_aap_job_template_node(self) -> None:
        wf = self._make_workflow(
            [
                {"id": "n1", "type": "aap_job_template", "parameters": {"job_template_id": 1}},
            ]
        )
        assert type(wf.nodes[0]).__name__ == "AAPJobTemplateNode"

    def test_invalid_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make_workflow(
                [
                    {"id": "n1", "type": "nonexistent", "parameters": {}},
                ]
            )


class TestModelDumpExcludeDefaults:
    """Test that model_dump(exclude_defaults=True) preserves user data and drops defaults."""

    def test_drops_none_defaults(self) -> None:
        wf = WorkflowDefinition.model_validate(
            {
                "schema_version": "2.0.0",
                "name": "test",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "bash", "code": "echo"}}],
                "edges": [],
            }
        )
        dumped = wf.model_dump(exclude_defaults=True)
        node = dumped["nodes"][0]
        assert "name" not in node
        assert "description" not in node
        assert "settings" not in node
        assert "position" not in node

    def test_preserves_user_set_fields(self) -> None:
        wf = WorkflowDefinition.model_validate(
            {
                "schema_version": "2.0.0",
                "name": "test",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "n1",
                        "type": "script",
                        "name": "My Script",
                        "parameters": {"language": "bash", "code": "echo"},
                        "settings": {"timeout": 5},
                    }
                ],
                "edges": [],
            }
        )
        dumped = wf.model_dump(exclude_defaults=True)
        node = dumped["nodes"][0]
        assert node["name"] == "My Script"
        assert node["settings"]["timeout"] == 5

    def test_approval_approvers_preserved(self) -> None:
        wf = WorkflowDefinition.model_validate(
            {
                "schema_version": "2.0.0",
                "name": "test",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "n1",
                        "type": "approval",
                        "parameters": {
                            "approver_users": ["admin"],
                            "approver_groups": ["leads"],
                            "prompt": "Approve this",
                        },
                    }
                ],
                "edges": [],
            }
        )
        dumped = wf.model_dump(exclude_defaults=True)
        params = dumped["nodes"][0]["parameters"]
        assert params["approver_users"] == ["admin"]
        assert params["approver_groups"] == ["leads"]
        assert params["prompt"] == "Approve this"


class TestWorkflowNodeBaseFields:
    """Test that WorkflowNodeBase accepts all standard node fields."""

    def test_accepts_position(self) -> None:
        wf = WorkflowDefinition.model_validate(
            {
                "schema_version": "2.0.0",
                "name": "test",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "n1",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo"},
                        "position": {"x": 100.0, "y": 200.0},
                    }
                ],
                "edges": [],
            }
        )
        assert wf.nodes[0].position is not None
        assert wf.nodes[0].position.x == 100.0

    def test_accepts_outputs(self) -> None:
        wf = WorkflowDefinition.model_validate(
            {
                "schema_version": "2.0.0",
                "name": "test",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "n1",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo"},
                        "outputs": {"result": "${result.stdout}"},
                    }
                ],
                "edges": [],
            }
        )
        assert wf.nodes[0].outputs == {"result": "${result.stdout}"}


class TestRoundTrip:
    """Test that validate → dump → validate produces identical results (no data loss)."""

    _NODE_FIXTURES: ClassVar[list[dict[str, Any]]] = [
        {"id": "n1", "type": "script", "name": "S", "parameters": {"language": "bash", "code": "echo"}},
        {"id": "n2", "type": "http_request", "parameters": {"method": "GET", "url": "http://x.com"}},
        {"id": "n3", "type": "agentic", "parameters": {"prompt": "do"}},
        {"id": "n4", "type": "condition", "parameters": {"condition": "1==1"}},
        {
            "id": "n5",
            "type": "switch",
            "parameters": {"cases": [{"port": "c0", "label": "C0", "condition": "1==1"}]},
        },
        {"id": "n6", "type": "converge", "parameters": {}},
        {"id": "n7", "type": "wait", "parameters": {"duration": 5}},
        {"id": "n8", "type": "approval", "parameters": {"approver_users": ["admin"], "prompt": "ok"}},
        {"id": "n9", "type": "loop", "parameters": {"type": "for_each", "items": "${trigger.list}"}},
        {"id": "n10", "type": "loop", "parameters": {"type": "do_while", "condition": "x==1"}},
        {"id": "n11", "type": "aap_job_template", "parameters": {"job_template_id": 1}},
    ]

    @pytest.mark.parametrize("node_dict", _NODE_FIXTURES, ids=[n["type"] for n in _NODE_FIXTURES])
    def test_round_trip_no_data_loss(self, node_dict: dict[str, Any]) -> None:
        """Validate → dump → validate produces identical output for each node type."""
        wf_dict = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [node_dict],
            "edges": [],
        }
        wf1 = WorkflowDefinition.model_validate(wf_dict)
        dumped = wf1.model_dump(exclude_defaults=True)
        wf2 = WorkflowDefinition.model_validate(dumped)
        assert wf1.model_dump(exclude_defaults=True) == wf2.model_dump(exclude_defaults=True)


class TestDiscriminatorErrorMessages:
    """Test that discriminator validation produces clear error messages."""

    def test_unknown_type_error(self) -> None:
        """Unknown type value produces a clear validation error."""
        with pytest.raises(ValidationError, match="nonexistent"):
            WorkflowDefinition.model_validate(
                {
                    "schema_version": "2.0.0",
                    "name": "test",
                    "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                    "nodes": [{"id": "n1", "type": "nonexistent", "parameters": {}}],
                    "edges": [],
                }
            )

    def test_missing_type_error(self) -> None:
        """Missing type field produces a validation error."""
        with pytest.raises(ValidationError):
            WorkflowDefinition.model_validate(
                {
                    "schema_version": "2.0.0",
                    "name": "test",
                    "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                    "nodes": [{"id": "n1", "parameters": {}}],
                    "edges": [],
                }
            )


class TestSwitchCaseConditionValidation:
    """Test that SwitchCase.condition rejects empty strings."""

    def test_empty_condition_rejected(self) -> None:
        """Empty condition on a switch case is rejected at validation time."""
        with pytest.raises(ValidationError):
            SwitchCase(port="c0", label="Case 0", condition="")
