"""Tests for SubWorkflowOutput model (AAP-94069).

Covers StandardOutputWrapper structure per ANSTRAT-2422 R4:
- Result field contains child execution metadata
- StatusCode, StatusMessage, ErrorMessage top-level fields
- Field population and validation
- child_status enum validation
- Nullability semantics
- NodeOutput inheritance and dump() method
"""

import pytest

from syntara.workflows.workflow_engine.models.workflow_definition import (
    NodeOutput,
    StandardOutputWrapper,
    SubWorkflowOutput,
    SubWorkflowOutputResult,
)


class TestStandardOutputWrapper:
    """Verify StandardOutputWrapper structure per ANSTRAT-2422 R4."""

    def test_has_required_fields(self) -> None:
        """StandardOutputWrapper has Result, StatusCode, StatusMessage, ErrorMessage."""
        expected = {"Result", "StatusCode", "StatusMessage", "ErrorMessage"}
        assert set(StandardOutputWrapper.model_fields.keys()) == expected

    @pytest.mark.parametrize(
        "field_name",
        ["Result", "StatusCode", "StatusMessage", "ErrorMessage"],
    )
    def test_all_fields_default_to_none(self, field_name: str) -> None:
        """All fields default to None for flexibility."""
        wrapper = StandardOutputWrapper()
        assert getattr(wrapper, field_name) is None

    def test_can_create_with_values(self) -> None:
        """Can create StandardOutputWrapper with values."""
        wrapper = StandardOutputWrapper(
            Result={"deployment_url": "https://example.com"},
            StatusCode=0,
            StatusMessage="Deployment successful",
            ErrorMessage="",
        )
        assert wrapper.Result == {"deployment_url": "https://example.com"}
        assert wrapper.StatusCode == 0
        assert wrapper.StatusMessage == "Deployment successful"


class TestSubWorkflowOutputStandardWrapper:
    """Verify SubWorkflowOutput follows StandardOutputWrapper structure (ANSTRAT-2422 R4)."""

    @pytest.mark.parametrize(
        "field_name",
        ["Result", "StatusCode", "StatusMessage", "ErrorMessage"],
    )
    def test_all_wrapper_fields_default_to_none(self, field_name: str) -> None:
        """All StandardOutputWrapper fields default to None per NodeOutput pattern."""
        output = SubWorkflowOutput()
        assert getattr(output, field_name) is None


class TestSubWorkflowOutputResultContract:
    """Verify SubWorkflowOutputResult contains expected child execution fields."""

    def test_result_has_expected_fields(self) -> None:
        """SubWorkflowOutputResult has child execution fields from spike AAP-95060."""
        expected = {
            "child_execution_id",
            "child_workflow_id",
            "child_workflow_name",
            "child_workflow_version",
            "child_status",
            "outputs",
        }
        assert set(SubWorkflowOutputResult.model_fields.keys()) == expected

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
    def test_all_result_fields_default_to_none(self, field_name: str) -> None:
        """All Result fields default to None."""
        result = SubWorkflowOutputResult()
        assert getattr(result, field_name) is None


class TestSubWorkflowOutputPopulated:
    """Verify field population and validation."""

    @pytest.mark.parametrize(
        "status_value",
        ["running", "succeeded", "failed", "cancelled"],
    )
    def test_child_status_enum_values(self, status_value: str) -> None:
        """child_status accepts all valid enum values."""
        result = SubWorkflowOutputResult(
            child_workflow_id="test-id",
            child_workflow_name="Test",
            child_workflow_version=1,
            child_status=status_value,  # type: ignore[arg-type]
        )
        assert result.child_status == status_value

    @pytest.mark.parametrize(
        ("scenario", "result_data", "wrapper_data", "expected_status_code"),
        [
            (
                "minimal_success",
                {
                    "child_workflow_id": "wf-123",
                    "child_workflow_name": "Deploy",
                    "child_workflow_version": 1,
                },
                {"StatusCode": 0, "StatusMessage": "Invocation initiated"},
                0,
            ),
            (
                "full_success",
                {
                    "child_execution_id": "exec-123",
                    "child_workflow_id": "wf-456",
                    "child_workflow_name": "Deploy Application",
                    "child_workflow_version": 3,
                    "child_status": "succeeded",
                    "outputs": {
                        "step_1": StandardOutputWrapper(
                            Result={"status": "ok"}, StatusCode=0, StatusMessage="Step completed"
                        )
                    },
                },
                {"StatusCode": 0, "StatusMessage": "Sub-workflow completed successfully"},
                0,
            ),
            (
                "invocation_failure",
                {
                    "child_workflow_id": "wf-789",
                    "child_workflow_name": "Deploy",
                    "child_workflow_version": 1,
                    "child_execution_id": None,
                    "child_status": None,
                },
                {"StatusCode": 1, "ErrorMessage": "Permission denied"},
                1,
            ),
        ],
    )
    def test_standard_wrapper_population_scenarios(
        self, scenario: str, result_data: dict, wrapper_data: dict, expected_status_code: int
    ) -> None:
        """StandardOutputWrapper fields populate correctly for different scenarios."""
        result = SubWorkflowOutputResult(**result_data)
        output = SubWorkflowOutput(Result=result, **wrapper_data)

        assert output.StatusCode == expected_status_code
        assert output.Result is not None
        assert output.Result.child_workflow_id == result_data["child_workflow_id"]

    def test_outputs_multi_terminal_structure(self) -> None:
        """Outputs dict supports multiple child step outputs (multi-terminal scenario)."""
        outputs_data = {
            "deploy_us": StandardOutputWrapper(
                Result={"region": "us-east-1"}, StatusCode=0, StatusMessage="US deployed"
            ),
            "deploy_eu": StandardOutputWrapper(
                Result={"region": "eu-west-1"}, StatusCode=0, StatusMessage="EU deployed"
            ),
            "deploy_ap": StandardOutputWrapper(
                Result={"region": "ap-south-1"}, StatusCode=0, StatusMessage="AP deployed"
            ),
        }
        result = SubWorkflowOutputResult(
            child_workflow_id="wf-id",
            child_workflow_name="Multi-Region",
            child_workflow_version=1,
            outputs=outputs_data,
        )
        output = SubWorkflowOutput(Result=result, StatusCode=0)

        assert output.Result.outputs is not None
        assert len(output.Result.outputs) == 3
        assert all(key in output.Result.outputs for key in ["deploy_us", "deploy_eu", "deploy_ap"])
        # Verify they're StandardOutputWrapper instances
        assert all(isinstance(v, StandardOutputWrapper) for v in output.Result.outputs.values())


class TestSubWorkflowOutputNullabilitySemantics:
    """Verify nullability semantics per spike AAP-95060."""

    def test_outputs_null_when_child_succeeded_but_unauthorized(self) -> None:
        """Outputs is None when child succeeded but parent lacks read permission (OQ-5)."""
        result = SubWorkflowOutputResult(
            child_execution_id="exec-123",
            child_workflow_id="wf-456",
            child_workflow_name="Deploy",
            child_workflow_version=1,
            child_status="succeeded",
            outputs=None,  # Null due to authorization denial
        )
        output = SubWorkflowOutput(
            Result=result,
            StatusCode=0,
            StatusMessage="Sub-workflow completed (outputs not visible due to permissions)",
        )

        assert output.Result.child_status == "succeeded"
        assert output.Result.outputs is None
        assert output.StatusCode == 0


class TestSubWorkflowOutputInheritanceAndSerialization:
    """Verify NodeOutput inheritance and dump() method."""

    def test_inherits_from_node_output(self) -> None:
        """SubWorkflowOutput is a subclass of NodeOutput with dump() method."""
        assert issubclass(SubWorkflowOutput, NodeOutput)
        output = SubWorkflowOutput()
        assert isinstance(output, NodeOutput)
        assert hasattr(output, "dump")
        assert callable(output.dump)

    @pytest.mark.parametrize(
        ("output_config", "expected_keys"),
        [
            (
                None,
                {"Result", "StatusCode", "StatusMessage", "ErrorMessage"},
            ),  # Passthrough - all wrapper fields
            ({}, set()),  # Empty mapping filters all
            (
                {"exec_id": "${result.Result.child_execution_id}", "status": "${result.StatusCode}"},
                {"exec_id", "status"},
            ),  # Selective mapping
        ],
    )
    def test_dump_with_output_mapping(self, output_config: dict | None, expected_keys: set) -> None:
        """dump() applies output mapping correctly."""
        result = SubWorkflowOutputResult(
            child_execution_id="exec-123",
            child_workflow_id="wf-456",
            child_workflow_name="Deploy",
            child_workflow_version=3,
            child_status="succeeded",
            outputs={"step_1": StandardOutputWrapper(Result={"status": "ok"}, StatusCode=0, StatusMessage="Completed")},
        )
        output = SubWorkflowOutput(
            Result=result,
            StatusCode=0,
            StatusMessage="Sub-workflow completed successfully",
            ErrorMessage="",
        )
        dumped = output.dump(output_config=output_config)
        assert set(dumped.keys()) == expected_keys

    def test_model_dump_exclude_none(self) -> None:
        """model_dump(exclude_none=True) omits None fields."""
        result = SubWorkflowOutputResult(
            child_workflow_id="wf-123",
            child_workflow_name="Test",
            child_workflow_version=1,
        )
        output = SubWorkflowOutput(Result=result, StatusCode=0)

        dumped = output.model_dump(exclude_none=True)
        assert "Result" in dumped
        assert "StatusCode" in dumped
        # ErrorMessage and StatusMessage are None, so excluded
        assert "StatusMessage" not in dumped
        assert "ErrorMessage" not in dumped
