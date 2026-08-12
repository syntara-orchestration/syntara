"""Tests for NodeOutput models and the NODE_OUTPUT_MODELS registry.

Covers:
- ApprovalOutput field naming (decided_by, decided_at, decision_notes per domain convention)
- ApprovalOutput status field with ActivityTerminalStatus
- NodeOutput.dump() with and without output mapping
- All NodeOutput subclass default values and field population
- model_dump(exclude_none=True) behavior used by approval_mixin
- NODE_OUTPUT_MODELS registry completeness
"""

from typing import Any

import pytest

from syntara.workflows.workflow_engine.models.workflow_definition import (
    NODE_OUTPUT_MODELS,
    AAPJobTemplateOutput,
    AAPWorkflowJobTemplateOutput,
    ActivityTerminalStatus,
    AgenticOutput,
    ApprovalOutput,
    ConditionOutput,
    ConvergeOutput,
    HttpRequestOutput,
    LoopOutput,
    NodeOutput,
    NodeType,
    ScriptOutput,
    SwitchOutput,
    WaitOutput,
)


class TestApprovalOutputFieldNaming:
    """Verify ApprovalOutput uses the domain convention field names."""

    def test_field_names_match_domain_convention(self) -> None:
        """ApprovalOutput fields use decided_by/decided_at/decision_notes, not approver/timestamp/comments."""
        field_names = set(ApprovalOutput.model_fields.keys())
        assert "decided_by" in field_names
        assert "decided_at" in field_names
        assert "decision_notes" in field_names

    def test_old_field_names_absent(self) -> None:
        """Old field names (approver, timestamp, comments) must not exist."""
        field_names = set(ApprovalOutput.model_fields.keys())
        assert "approver" not in field_names
        assert "timestamp" not in field_names
        assert "comments" not in field_names

    def test_has_status_field(self) -> None:
        """ApprovalOutput includes a status field for ActivityTerminalStatus."""
        assert "status" in ApprovalOutput.model_fields

    def test_has_decision_field(self) -> None:
        """ApprovalOutput includes a decision field."""
        assert "decision" in ApprovalOutput.model_fields

    def test_all_expected_fields_present(self) -> None:
        """ApprovalOutput has exactly the expected set of fields."""
        expected = {"status", "decision", "decided_by", "decided_at", "decision_notes"}
        assert set(ApprovalOutput.model_fields.keys()) == expected


class TestApprovalOutputDefaults:
    """Verify all ApprovalOutput fields default to None."""

    def test_all_fields_default_to_none(self) -> None:
        output = ApprovalOutput()
        assert output.status is None
        assert output.decision is None
        assert output.decided_by is None
        assert output.decided_at is None
        assert output.decision_notes is None

    def test_model_dump_all_none(self) -> None:
        output = ApprovalOutput()
        dumped = output.model_dump()
        assert dumped == {
            "status": None,
            "decision": None,
            "decided_by": None,
            "decided_at": None,
            "decision_notes": None,
        }


class TestApprovalOutputPopulated:
    """Verify ApprovalOutput with populated field values."""

    def test_approved_output(self) -> None:
        output = ApprovalOutput(
            status=ActivityTerminalStatus.COMPLETED,
            decision="approved",
            decided_by="jsmith",
            decided_at="2026-05-20T10:00:00+00:00",
            decision_notes="LGTM",
        )
        assert output.status == ActivityTerminalStatus.COMPLETED
        assert output.decision == "approved"
        assert output.decided_by == "jsmith"
        assert output.decided_at == "2026-05-20T10:00:00+00:00"
        assert output.decision_notes == "LGTM"

    def test_rejected_output(self) -> None:
        output = ApprovalOutput(
            status=ActivityTerminalStatus.COMPLETED,
            decision="rejected",
            decided_by="admin",
            decided_at="2026-07-01T14:30:00Z",
            decision_notes="Not ready for production",
        )
        assert output.decision == "rejected"
        assert output.decided_by == "admin"
        assert output.decision_notes == "Not ready for production"

    def test_partial_fields(self) -> None:
        """Only decision and status set — other fields stay None."""
        output = ApprovalOutput(
            status=ActivityTerminalStatus.COMPLETED,
            decision="approved",
        )
        assert output.status == ActivityTerminalStatus.COMPLETED
        assert output.decision == "approved"
        assert output.decided_by is None
        assert output.decided_at is None
        assert output.decision_notes is None


class TestApprovalOutputStatus:
    """Verify the status field works with all ActivityTerminalStatus values."""

    @pytest.mark.parametrize("terminal_status", list(ActivityTerminalStatus))
    def test_accepts_all_terminal_statuses(self, terminal_status: ActivityTerminalStatus) -> None:
        output = ApprovalOutput(status=terminal_status)
        assert output.status == terminal_status

    def test_status_serialises_as_string(self) -> None:
        output = ApprovalOutput(status=ActivityTerminalStatus.COMPLETED)
        dumped = output.model_dump()
        assert dumped["status"] == "completed"

    def test_status_none_by_default(self) -> None:
        output = ApprovalOutput()
        assert output.status is None


class TestApprovalOutputExcludeNone:
    """Verify model_dump(exclude_none=True) matches how approval_mixin serialises output."""

    def test_exclude_none_full_output(self) -> None:
        output = ApprovalOutput(
            status=ActivityTerminalStatus.COMPLETED,
            decision="approved",
            decided_by="jsmith",
            decided_at="2026-05-20T10:00:00+00:00",
            decision_notes="LGTM",
        )
        dumped = output.model_dump(exclude_none=True)
        assert dumped == {
            "status": "completed",
            "decision": "approved",
            "decided_by": "jsmith",
            "decided_at": "2026-05-20T10:00:00+00:00",
            "decision_notes": "LGTM",
        }

    def test_exclude_none_without_notes(self) -> None:
        """decision_notes key is absent when not provided."""
        output = ApprovalOutput(
            status=ActivityTerminalStatus.COMPLETED,
            decision="rejected",
            decided_by="jsmith",
            decided_at="2026-05-20T10:00:00+00:00",
        )
        dumped = output.model_dump(exclude_none=True)
        assert "decision_notes" not in dumped
        assert dumped == {
            "status": "completed",
            "decision": "rejected",
            "decided_by": "jsmith",
            "decided_at": "2026-05-20T10:00:00+00:00",
        }

    def test_exclude_none_empty_output(self) -> None:
        """All-None ApprovalOutput produces empty dict with exclude_none."""
        output = ApprovalOutput()
        dumped = output.model_dump(exclude_none=True)
        assert dumped == {}

    def test_exclude_none_only_status(self) -> None:
        output = ApprovalOutput(status=ActivityTerminalStatus.CANCELLED)
        dumped = output.model_dump(exclude_none=True)
        assert dumped == {"status": "cancelled"}


class TestApprovalOutputIsNodeOutput:
    """Verify ApprovalOutput inherits from NodeOutput."""

    def test_is_subclass(self) -> None:
        assert issubclass(ApprovalOutput, NodeOutput)

    def test_instance_check(self) -> None:
        output = ApprovalOutput()
        assert isinstance(output, NodeOutput)

    def test_has_dump_method(self) -> None:
        output = ApprovalOutput()
        assert hasattr(output, "dump")
        assert callable(output.dump)


class TestNodeOutputDump:
    """Verify NodeOutput.dump() with and without output mapping."""

    def test_dump_without_mapping_returns_full_model(self) -> None:
        output = ApprovalOutput(
            status=ActivityTerminalStatus.COMPLETED,
            decision="approved",
            decided_by="jsmith",
            decided_at="2026-05-20T10:00:00+00:00",
            decision_notes="LGTM",
        )
        dumped = output.dump()
        assert dumped["status"] == "completed"
        assert dumped["decision"] == "approved"
        assert dumped["decided_by"] == "jsmith"

    def test_dump_with_empty_mapping_returns_empty(self) -> None:
        output = ApprovalOutput(
            status=ActivityTerminalStatus.COMPLETED,
            decision="approved",
        )
        dumped = output.dump(output_config={})
        assert dumped == {}

    def test_dump_with_selective_mapping(self) -> None:
        output = ScriptOutput(
            return_code=0,
            stdout="hello world",
            stderr="",
            stdout_json=None,
        )
        dumped = output.dump(output_config={"exit_code": "${result.return_code}"})
        assert dumped == {"exit_code": 0}

    def test_dump_none_mapping_is_passthrough(self) -> None:
        output = HttpRequestOutput(status_code=200, body={"ok": True})
        dumped = output.dump(output_config=None)
        assert dumped["status_code"] == 200
        assert dumped["body"] == {"ok": True}


class TestScriptOutputDefaults:
    """Verify ScriptOutput field defaults."""

    def test_all_fields_default_to_none(self) -> None:
        output = ScriptOutput()
        assert output.return_code is None
        assert output.stdout is None
        assert output.stderr is None
        assert output.stdout_json is None

    def test_populated(self) -> None:
        output = ScriptOutput(return_code=0, stdout="ok", stderr="", stdout_json={"key": "val"})
        assert output.return_code == 0
        assert output.stdout == "ok"
        assert output.stderr == ""
        assert output.stdout_json == {"key": "val"}


class TestHttpRequestOutputDefaults:
    """Verify HttpRequestOutput field defaults."""

    def test_all_fields_default_to_none(self) -> None:
        output = HttpRequestOutput()
        assert output.status_code is None
        assert output.body is None
        assert output.headers is None
        assert output.elapsed is None

    def test_populated(self) -> None:
        output = HttpRequestOutput(
            status_code=201,
            body={"id": 1},
            headers={"content-type": "application/json"},
            elapsed=0.123,
        )
        assert output.status_code == 201
        assert output.elapsed == 0.123


class TestAAPJobTemplateOutputDefaults:
    """Verify AAPJobTemplateOutput field defaults."""

    def test_all_fields_default_to_none(self) -> None:
        output = AAPJobTemplateOutput()
        assert output.job_id is None
        assert output.job_url is None
        assert output.job_status is None
        assert output.artifacts is None
        assert output.created is None
        assert output.started is None
        assert output.finished is None

    def test_populated(self) -> None:
        output = AAPJobTemplateOutput(
            job_id=42,
            job_url="https://aap.example.com/jobs/42",
            job_status="successful",
            artifacts={"results": "clean"},
            created="2026-01-01T00:00:00Z",
            started="2026-01-01T00:00:01Z",
            finished="2026-01-01T00:01:00Z",
        )
        assert output.job_id == 42
        assert output.job_status == "successful"


class TestAAPWorkflowJobTemplateOutputDefaults:
    """Verify AAPWorkflowJobTemplateOutput field defaults."""

    def test_all_fields_default_to_none(self) -> None:
        output = AAPWorkflowJobTemplateOutput()
        assert output.workflow_job_id is None
        assert output.workflow_job_url is None
        assert output.workflow_job_status is None
        assert output.artifacts is None
        assert output.created is None
        assert output.started is None
        assert output.finished is None


class TestAgenticOutputDefaults:
    """Verify AgenticOutput field defaults."""

    def test_all_fields_default_to_none(self) -> None:
        output = AgenticOutput()
        assert output.output is None
        assert output.tool_calls is None
        assert output.used_tools is None
        assert output.structured_output_metadata is None
        assert output.integration_ids is None

    def test_output_accepts_string(self) -> None:
        output = AgenticOutput(output="Agent response text")
        assert output.output == "Agent response text"

    def test_output_accepts_dict(self) -> None:
        output = AgenticOutput(output={"answer": 42})
        assert output.output == {"answer": 42}


class TestConditionOutputDefaults:
    """Verify ConditionOutput field defaults."""

    def test_default_none(self) -> None:
        output = ConditionOutput()
        assert output.evaluated_result is None

    @pytest.mark.parametrize("value", [True, False])
    def test_boolean_values(self, *, value: bool) -> None:
        output = ConditionOutput(evaluated_result=value)
        assert output.evaluated_result is value


class TestSwitchOutputDefaults:
    """Verify SwitchOutput field defaults."""

    def test_default_none(self) -> None:
        output = SwitchOutput()
        assert output.matched_port is None

    def test_populated(self) -> None:
        output = SwitchOutput(matched_port="case_1")
        assert output.matched_port == "case_1"


class TestConvergeOutputDefaults:
    """Verify ConvergeOutput field defaults."""

    def test_all_fields_default_to_none(self) -> None:
        output = ConvergeOutput()
        assert output.branch_count is None
        assert output.completed_count is None
        assert output.completed_branch_node_ids is None

    def test_populated(self) -> None:
        output = ConvergeOutput(
            branch_count=3,
            completed_count=2,
            completed_branch_node_ids=["a", "b"],
        )
        assert output.branch_count == 3
        assert output.completed_branch_node_ids == ["a", "b"]


class TestLoopOutputDefaults:
    """Verify LoopOutput field defaults."""

    def test_all_fields_default_to_none(self) -> None:
        output = LoopOutput()
        assert output.iteration_count is None
        assert output.iteration_results is None

    def test_populated(self) -> None:
        output = LoopOutput(
            iteration_count=3,
            iteration_results={"node_a": [1, 2, 3]},
        )
        assert output.iteration_count == 3


class TestWaitOutputDefaults:
    """Verify WaitOutput has no extra fields beyond NodeOutput."""

    def test_no_custom_fields(self) -> None:
        assert len(WaitOutput.model_fields) == 0

    def test_instantiation(self) -> None:
        output = WaitOutput()
        assert isinstance(output, NodeOutput)

    def test_dump_empty(self) -> None:
        output = WaitOutput()
        assert output.dump() == {}


class TestNodeOutputModelsRegistry:
    """Verify NODE_OUTPUT_MODELS registry is complete and correct."""

    def test_registry_maps_all_expected_node_types(self) -> None:
        expected_types = {
            NodeType.SCRIPT,
            NodeType.HTTP_REQUEST,
            NodeType.AAP_JOB_TEMPLATE,
            NodeType.AAP_WORKFLOW_JOB_TEMPLATE,
            NodeType.AGENTIC,
            NodeType.APPROVAL,
            NodeType.CONDITION,
            NodeType.SWITCH,
            NodeType.CONVERGE,
            NodeType.LOOP,
            NodeType.WAIT,
        }
        assert set(NODE_OUTPUT_MODELS.keys()) == expected_types

    def test_approval_maps_to_approval_output(self) -> None:
        assert NODE_OUTPUT_MODELS[NodeType.APPROVAL] is ApprovalOutput

    def test_all_values_are_node_output_subclasses(self) -> None:
        for node_type, model_cls in NODE_OUTPUT_MODELS.items():
            assert issubclass(model_cls, NodeOutput), f"{node_type} -> {model_cls} is not a NodeOutput subclass"

    def test_each_model_instantiates_with_no_args(self) -> None:
        """Every registered model can be created with all defaults (uniform shape guarantee)."""
        for node_type, model_cls in NODE_OUTPUT_MODELS.items():
            instance = model_cls()
            assert isinstance(instance, NodeOutput), f"{node_type} failed default instantiation"

    def test_each_model_dump_returns_dict(self) -> None:
        for node_type, model_cls in NODE_OUTPUT_MODELS.items():
            instance = model_cls()
            dumped = instance.dump()
            assert isinstance(dumped, dict), f"{node_type}.dump() did not return dict"


class TestNodeOutputModelDumpRoundTrip:
    """Verify model_dump -> model_validate round-trip for output models."""

    @pytest.mark.parametrize(
        ("model_cls", "fields"),
        [
            (ApprovalOutput, {"status": "completed", "decision": "approved", "decided_by": "user1"}),
            (ScriptOutput, {"return_code": 0, "stdout": "ok"}),
            (HttpRequestOutput, {"status_code": 200, "body": {"key": "val"}}),
            (ConditionOutput, {"evaluated_result": True}),
            (SwitchOutput, {"matched_port": "case_a"}),
        ],
    )
    def test_round_trip(self, model_cls: type[NodeOutput], fields: dict[str, Any]) -> None:
        original = model_cls(**fields)
        dumped = original.model_dump()
        restored = model_cls.model_validate(dumped)
        assert restored.model_dump() == dumped
