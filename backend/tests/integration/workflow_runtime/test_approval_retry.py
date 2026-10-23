"""Approval retry and cleanup through the registered domain provider."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.approvals.activities import ApprovalActivities
from syntara.approvals.models.approval_request import ApprovalRequest
from syntara.approvals.registration import register_approval_activities
from syntara.core.lib.encryption import SecretEncryptor
from syntara.core.models.principal import Principal
from syntara.workflow_runtime.completion import CompletionService
from syntara.workflow_runtime.contracts import ActivityError
from syntara.workflow_runtime.engines.temporal.registered_activities import RegisteredActivities
from syntara.workflow_runtime.models import ActivityCompletion
from syntara.workflow_runtime.registry import ActivityRegistry
from syntara.workflows.models.execution import Execution
from tests.fixtures.temporal import CompleteAsyncError


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup", ["expire", "cancel"])
async def test_retry_reuses_approval_and_cleanup_closes_current_attempt(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_execution: Execution,
    cleanup: str,
) -> None:
    """New attempts replace the reference, while preserving the logical request."""
    test_db_session.add(Principal.for_service("worker.ao.svc"))
    await test_db_session.commit()
    registry = ActivityRegistry()
    register_approval_activities(registry, ApprovalActivities(test_db_session_factory))
    adapter = RegisteredActivities(registry, test_db_session_factory, SecretEncryptor(bytes(range(32))))
    info = MagicMock(
        activity_id="review_iter_2",
        workflow_id="test",
        workflow_run_id=str(uuid4()),
        attempt=1,
        task_token=b"attempt-one",
        started_time=datetime.now(UTC),
        start_to_close_timeout=timedelta(hours=1),
    )
    request = {
        "name": "approval.request",
        "version": 1,
        "execution_id": str(test_execution.id),
        "project_id": str(test_execution.project_id),
        "input": {
            "name": "Review",
            "approval_node_id": "review",
            "loop_iteration_path": [2],
            "workflow_context": {"workflow_id": str(test_execution.workflow_id), "workflow_name": "Test", "inputs": {}},
            "next_step_approved": {"id": "next", "name": "Next", "type": "script"},
        },
    }
    with patch("temporalio.activity.info", return_value=info), patch("temporalio.activity.heartbeat"):
        for attempt in (1, 2):
            info.attempt = attempt
            info.task_token = f"attempt-{attempt}".encode()
            with pytest.raises(CompleteAsyncError):
                await adapter.execute(request)
        async with test_db_session_factory() as session:
            approvals = (await session.exec(select(ApprovalRequest))).all()
            assert len(approvals) == 1
            approval = approvals[0]
            rows = (await session.exec(select(ActivityCompletion).order_by(col(ActivityCompletion.attempt)))).all()
            assert [row.state for row in rows] == ["obsolete", "reserved"]
            assert approval.completion_ref == rows[1].id
            assert rows[1].deferred
            with pytest.raises(ActivityError, match="closed"):
                await CompletionService(session).complete(
                    rows[0].id,
                    execution_id=test_execution.id,
                    project_id=test_execution.project_id,
                    output={"decision": "approved"},
                )
        result = await adapter.execute({**request, "name": f"approval.{cleanup}", "input": {}})
        key = "expired_count" if cleanup == "expire" else "cancelled_count"
        assert result == {"output": {key: 1}}
        async with test_db_session_factory() as session:
            saved = await session.get(ApprovalRequest, approval.id)
            current = await session.get(ActivityCompletion, rows[1].id)
            assert saved is not None
            assert saved.status.value == ("expired" if cleanup == "expire" else "cancelled")
            assert current is not None
            assert current.state == "obsolete"
