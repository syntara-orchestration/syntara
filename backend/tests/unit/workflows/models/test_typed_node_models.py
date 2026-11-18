"""Unit tests for typed workflow node models and control node parameters.

Tests validation, discriminated union resolution, and model_dump behavior
for the WorkflowNode typed models introduced in AAP-77227.
"""

from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from syntara.forms.models.form_fields import FormPromptDefinition, TextField
from syntara.workflow_core.models import (
    ApprovalNodeParameters,
    ConditionNodeParameters,
    ConvergeNodeParameters,
    DoWhileLoopParameters,
    ForEachLoopParameters,
    FormPromptNodeParameters,
    SwitchCase,
    SwitchNodeParameters,
    WaitNodeParameters,
)
from syntara.workflows.models.workflow_definition import WorkflowDefinition


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


class TestFormPromptNodeParameters:
    """Tests for FormPromptNodeParameters validation."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.form_def = self._minimal_form_definition()

    @staticmethod
    def _minimal_form_definition() -> FormPromptDefinition:
        """Return a minimal valid authored prompt definition."""
        return FormPromptDefinition(
            fields=[
                TextField(
                    type="text",
                    value_name="reason",
                    label="Reason",
                    required=False,
                )
            ]
        )

    def test_minimal_valid(self) -> None:
        """Minimal valid config with form_definition only."""
        p = FormPromptNodeParameters(form_definition=self.form_def)
        assert isinstance(p.form_definition, FormPromptDefinition)
        assert len(p.form_definition.fields) == 1
        assert p.form_definition.fields[0].value_name == "reason"
        assert p.message is None
        assert p.fallback_decision is None

    @pytest.mark.parametrize("field_type", ["dropdown", "multi_select"])
    def test_resolved_options_rejected_in_authored_definition(self, field_type: str) -> None:
        """Runtime-materialized option snapshots cannot be authored in workflows."""
        form_definition = {
            "fields": [
                {
                    "type": field_type,
                    "value_name": "region",
                    "label": "Region",
                    "options": {
                        "source": "dynamic_resolved",
                        "values": [{"display_label": "US", "value": 1}],
                    },
                }
            ]
        }

        with pytest.raises(ValidationError, match="Input tag 'dynamic_resolved'") as exc_info:
            FormPromptNodeParameters.model_validate({"form_definition": form_definition})

        assert len(exc_info.value.errors()) == 1
        assert "does not match any of the expected tags" in str(exc_info.value)

    @pytest.mark.parametrize("field_type", ["dropdown", "multi_select"])
    def test_static_and_dynamic_options_remain_authored_sources(self, field_type: str) -> None:
        """Static and dynamic source definitions remain valid for authors."""
        for options in (
            {"source": "static", "values": [{"display_label": "US", "value": "us"}]},
            {
                "source": "dynamic",
                "expression": "${fetch.output.regions}",
                "label_key": "display_label",
                "value_key": "value",
            },
        ):
            form_definition = {
                "fields": [
                    {
                        "type": field_type,
                        "value_name": "region",
                        "label": "Region",
                        "options": options,
                    }
                ]
            }
            parameters = FormPromptNodeParameters.model_validate({"form_definition": form_definition})
            assert parameters.form_definition.model_dump()["fields"][0]["options"]["source"] == options["source"]

    def test_fully_populated(self) -> None:
        """All fields populated."""
        p = FormPromptNodeParameters(
            message="Please fill out the form",
            form_definition=self.form_def,
            responder_users=["alice", "bob"],
            responder_groups=["team-a"],
            response_window=3600,
            fallback_decision="fallback",
            submit_label="Send",
            success_message="Thanks!",
        )
        assert p.message == "Please fill out the form"
        assert p.responder_users == ["alice", "bob"]
        assert p.response_window == 3600
        assert p.fallback_decision == "fallback"

    def test_missing_form_definition(self) -> None:
        """form_definition is required."""
        with pytest.raises(ValidationError):
            FormPromptNodeParameters()  # type: ignore[call-arg]

    def test_response_window_zero_rejected(self) -> None:
        """response_window=0 violates ge=1."""
        with pytest.raises(ValidationError):
            FormPromptNodeParameters(form_definition=self.form_def, response_window=0)

    def test_response_window_negative_rejected(self) -> None:
        """Negative response_window is rejected."""
        with pytest.raises(ValidationError):
            FormPromptNodeParameters(form_definition=self.form_def, response_window=-1)

    def test_responder_users_max_100(self) -> None:
        """responder_users max 100 entries."""
        with pytest.raises(ValidationError):
            FormPromptNodeParameters(form_definition=self.form_def, responder_users=["user"] * 101)

    def test_responder_groups_max_50(self) -> None:
        """responder_groups max 50 entries."""
        with pytest.raises(ValidationError):
            FormPromptNodeParameters(form_definition=self.form_def, responder_groups=["group"] * 51)

    def test_message_max_2000(self) -> None:
        """Message max 2000 chars."""
        with pytest.raises(ValidationError):
            FormPromptNodeParameters(form_definition=self.form_def, message="x" * 2001)

    def test_invalid_fallback_decision(self) -> None:
        """Invalid fallback_decision value rejected."""
        with pytest.raises(ValidationError):
            FormPromptNodeParameters(form_definition=self.form_def, fallback_decision="invalid")  # type: ignore[arg-type]

    def test_unknown_parameter_rejected(self) -> None:
        """extra='forbid' rejects unknown keys."""
        with pytest.raises(ValidationError):
            FormPromptNodeParameters(form_definition=self.form_def, unknown_field="value")  # type: ignore[call-arg]

    def test_template_in_message(self) -> None:
        """Template expressions survive in message."""
        p = FormPromptNodeParameters(form_definition=self.form_def, message="User: ${trigger.username}")
        assert p.message == "User: ${trigger.username}"

    def test_discriminated_union(self) -> None:
        """form_prompt parses through WorkflowDefinition."""
        wf = WorkflowDefinition.model_validate(
            {
                "schema_version": "2.0.0",
                "name": "test",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "form_node",
                        "type": "form_prompt",
                        "parameters": {"form_definition": self._minimal_form_definition()},
                    }
                ],
                "edges": [],
            }
        )
        assert wf.nodes[0].type == "form_prompt"
