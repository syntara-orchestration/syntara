"""Tests for the Sub-workflow output model."""

import pytest
from pydantic import ValidationError

from syntara.workflows.workflow_engine.models.workflow_definition import (
    JSONValue,
    NodeOutput,
    SubWorkflowOutput,
    WorkflowTerminalStatus,
)


class TestSubWorkflowOutput:
    """Verify the direct Sub-workflow result schema and value validation."""

    def test_result_fields_are_direct_and_do_not_include_wrapper_fields(self) -> None:
        expected = {
            "child_execution_id",
            "child_workflow_id",
            "child_workflow_name",
            "child_workflow_version",
            "child_status",
            "outputs",
        }
        assert set(SubWorkflowOutput.model_fields) == expected
        assert issubclass(SubWorkflowOutput, NodeOutput)

    @pytest.mark.parametrize(
        "field_name",
        [
            "child_execution_id",
            "child_workflow_id",
            "child_workflow_name",
            "child_workflow_version",
            "child_status",
            "outputs",
        ],
    )
    def test_fields_default_to_none(self, field_name: str) -> None:
        assert getattr(SubWorkflowOutput(), field_name) is None

    @pytest.mark.parametrize("status_value", ["completed", "completed_with_errors", "failed", "cancelled"])
    def test_child_status_accepts_terminal_values(self, status_value: str) -> None:
        output = SubWorkflowOutput(child_status=WorkflowTerminalStatus(status_value))
        assert output.child_status == status_value

    def test_outputs_accept_recursive_json_values(self) -> None:
        outputs: dict[str, JSONValue] = {
            "release_tag": "v3.2.1",
            "published": True,
            "build_number": 42,
            "artifacts": [{"url": "https://example.test/app", "labels": ["stable", "linux"]}],
            "metadata": {"optional": None},
        }
        output = SubWorkflowOutput(outputs=outputs)

        assert output.outputs == outputs
        assert output.model_dump()["outputs"] == outputs
        assert "Result" not in output.model_dump()
        assert "StatusCode" not in output.model_dump()

    @pytest.mark.parametrize(
        "invalid_value",
        [{"nested": b"not-json"}, float("nan")],
    )
    def test_outputs_reject_non_json_values(self, invalid_value: object) -> None:
        with pytest.raises(ValidationError):
            SubWorkflowOutput.model_validate({"outputs": {"release": invalid_value}})

    def test_child_status_can_be_null_when_no_child_execution_started(self) -> None:
        output = SubWorkflowOutput(child_workflow_id="wf-789", child_status=None, outputs=None)

        assert output.child_workflow_id == "wf-789"
        assert output.child_status is None
        assert output.outputs is None

    def test_child_workflow_name_length_constraint(self) -> None:
        with pytest.raises(ValidationError, match="at most 255 characters"):
            SubWorkflowOutput(child_workflow_name="x" * 256)

    def test_outputs_dict_size_constraint(self) -> None:
        large_outputs: dict[str, JSONValue] = {f"field_{index}": f"value_{index}" for index in range(1001)}
        with pytest.raises(ValidationError, match="at most 1000"):
            SubWorkflowOutput(outputs=large_outputs)

    def test_dump_applies_output_mapping_to_direct_fields(self) -> None:
        output = SubWorkflowOutput(
            child_execution_id="exec-123",
            child_status=WorkflowTerminalStatus.COMPLETED,
            outputs={"release_tag": "v3.2.1"},
        )

        dumped = output.dump(
            output_config={"exec_id": "${result.child_execution_id}", "status": "${result.child_status}"}
        )

        assert dumped == {"exec_id": "exec-123", "status": "completed"}

    def test_model_dump_excludes_none_fields(self) -> None:
        output = SubWorkflowOutput(child_workflow_id="wf-123", child_status=WorkflowTerminalStatus.COMPLETED)

        assert output.model_dump(exclude_none=True) == {
            "child_workflow_id": "wf-123",
            "child_status": "completed",
        }
