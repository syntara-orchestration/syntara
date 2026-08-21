"""Tests for the execution_error_summary helper on the Execution model."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from syntara.workflows.models.execution import Execution, ExecutionStatus, execution_error_summary


def _make_execution(status: ExecutionStatus, error_details: str | None) -> Execution:
    return Execution(
        id=uuid4(),
        workflow_id=uuid4(),
        workflow_version_id=uuid4(),
        temporal_workflow_id=f"temporal-exec-{uuid4()}",
        status=status,
        created_by=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        updated_by=uuid4(),
        input_data={},
        error_details=error_details,
        labels={},
        project_id=uuid4(),
    )


class TestExecutionErrorSummary:
    """Single source of truth shared by the REST response and the WS snapshot.

    Both ExecutionsConvertResourceMixin.convert_resource and
    ActivityUpdatePublisher._serialize_execution_snapshot delegate to this
    function rather than re-deriving the rule — this test is the one place
    the rule itself needs verifying.
    """

    @pytest.mark.parametrize(
        ("status", "error_details", "expected"),
        [
            (ExecutionStatus.FAILED, "node_b: KeyError: nonexistent_field", "node_b: KeyError: nonexistent_field"),
            (
                ExecutionStatus.COMPLETED_WITH_ERRORS,
                "node_bad: KeyError: nonexistent_field",
                "node_bad: KeyError: nonexistent_field",
            ),
            (ExecutionStatus.COMPLETED, None, None),
            (ExecutionStatus.RUNNING, None, None),
            (ExecutionStatus.PENDING, None, None),
            (ExecutionStatus.CANCELLED, None, None),
            # Defensive: error_details set but status not a failure status — summary stays null.
            (ExecutionStatus.COMPLETED, "stale error_details from a prior state", None),
            # Failure status but no error_details recorded (e.g. reconciliation edge case).
            (ExecutionStatus.FAILED, None, None),
        ],
    )
    def test_summary_only_populated_for_failure_statuses(
        self,
        status: ExecutionStatus,
        error_details: str | None,
        expected: str | None,
    ) -> None:
        execution = _make_execution(status, error_details)
        assert execution_error_summary(execution) == expected
