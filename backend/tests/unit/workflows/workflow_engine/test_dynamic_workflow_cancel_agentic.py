"""Regression tests for OrchestratorWorkflow._cancel_agentic_invocations.

The best-effort cancel path logs through ``workflow.logger``, which is a stdlib
``logging.Logger`` — it rejects arbitrary keyword arguments. A bare kwarg raised
``TypeError`` *inside the workflow*, which fails the workflow task; Temporal then
retried the activation forever and the execution never left RUNNING. Ref: AAP-88614.

These tests deliberately use a REAL logger. The shared ``_mock_temporal_workflow``
helper assigns a ``MagicMock`` logger, which silently accepts any kwarg and so
cannot catch this class of bug.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow


def _make_minimal_workflow() -> OrchestratorWorkflow:
    """Create an OrchestratorWorkflow with only what the cancel path touches."""
    wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
    wf.execution_id = "11111111-2222-3333-4444-555555555555"
    return wf


@pytest.mark.asyncio
@pytest.mark.parametrize("node_id", ["agent", None])
async def test_cancel_agentic_invocations_swallows_activity_failure(node_id: str | None) -> None:
    """A failing cancel activity must stay best-effort, not raise out of the workflow.

    Raising here fails the workflow task, and Temporal retries the activation
    indefinitely — the execution hangs in RUNNING and can never be cancelled.
    """
    wf = _make_minimal_workflow()

    with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf:
        # A real stdlib logger, exactly like the one Temporal injects. A MagicMock
        # would accept any kwarg and hide the defect this test exists to catch.
        mock_wf.logger = logging.getLogger("test.cancel_agentic")
        mock_wf.execute_activity = AsyncMock(side_effect=RuntimeError("activity blew up"))
        mock_wf.info.return_value = MagicMock(workflow_id="test-wf-id")

        await wf._cancel_agentic_invocations(node_id=node_id)

    assert mock_wf.execute_activity.await_count == 1


@pytest.mark.asyncio
async def test_cancel_agentic_invocations_swallows_temporal_cancellation() -> None:
    """Cancellation of the shielded activity is an Exception subclass in temporalio.

    When the parent workflow is cancelled, the pending cancel activity surfaces a
    temporalio CancelledError, which subclasses Exception and therefore reaches the
    same best-effort handler.
    """
    from temporalio.exceptions import CancelledError as TemporalCancelledError

    wf = _make_minimal_workflow()

    with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf:
        mock_wf.logger = logging.getLogger("test.cancel_agentic")
        mock_wf.execute_activity = AsyncMock(side_effect=TemporalCancelledError("cancelled"))
        mock_wf.info.return_value = MagicMock(workflow_id="test-wf-id")

        await wf._cancel_agentic_invocations(node_id="agent")


@pytest.mark.asyncio
async def test_cancel_agentic_invocations_returns_cleanly_on_success() -> None:
    """The happy path still awaits the activity and returns without logging a warning."""
    wf = _make_minimal_workflow()

    with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf:
        mock_wf.logger = logging.getLogger("test.cancel_agentic")
        mock_wf.execute_activity = AsyncMock(return_value={"attempted_count": 0})
        mock_wf.info.return_value = MagicMock(workflow_id="test-wf-id")

        await wf._cancel_agentic_invocations(node_id="agent")

    assert mock_wf.execute_activity.await_count == 1
