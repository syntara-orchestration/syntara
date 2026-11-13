"""Use real AO state to scope cancellation and snapshot deletion before cascades."""

from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4, uuid5

import pytest
from sqlmodel import select

from syntara.execution_plane import deletion
from syntara.execution_plane.reconciliation import reconcile_work_item_cancellations
from syntara.projects.service import ProjectService
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.services.workflow_service import WorkflowService

pytestmark = pytest.mark.integration


async def _seed_activities(session, execution) -> UUID:
    base_id = uuid5(execution.id, "script-node")
    for item_id, name, node_type, iteration in (
        (base_id, "script-node", "script", None),
        (uuid4(), "script-node[1]", "script", 1),
        (uuid5(execution.id, "http-node"), "http-node", "http_request", None),
        (uuid4(), "unrelated-node", "script", None),
    ):
        session.add(
            ActivityExecution(
                id=item_id,
                execution_id=execution.id,
                activity_name=name,
                temporal_activity_id=name,
                node_type=node_type,
                iteration=iteration,
                status=ActivityStatus.COMPLETED,
                retry_count=0,
            )
        )
    await session.commit()
    return base_id


@pytest.mark.parametrize("status", [ExecutionStatus.CANCELLED, ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED])
async def test_reconciliation_only_cancels_work_for_cancelled_executions(test_db_session, test_execution, status):
    item_id = await _seed_activities(test_db_session, test_execution)
    test_execution.status = status
    await test_db_session.commit()
    client = AsyncMock()
    client.list_work_items.return_value = {"resources": [{"id": str(item_id)}, {"id": str(uuid4())}], "next": None}

    assert await reconcile_work_item_cancellations(test_db_session, client) == int(status is ExecutionStatus.CANCELLED)
    if status is ExecutionStatus.CANCELLED:
        client.cancel_work_item.assert_awaited_once_with(work_item_id=item_id)
    else:
        client.cancel_work_item.assert_not_awaited()
    client.delete_work_item.assert_not_awaited()


@pytest.mark.parametrize("scope", ["project", "workflow"])
async def test_deletion_collects_base_identities_independent_of_current_images(test_db_session, test_execution, scope):
    item_id = await _seed_activities(test_db_session, test_execution)
    owner_id = test_execution.project_id if scope == "project" else test_execution.workflow_id
    assert await deletion.collect_execution_plane_work_items(test_db_session, **{f"{scope}_id": owner_id}) == sorted(
        [item_id, uuid5(test_execution.id, "http-node")]
    )
    assert await deletion.collect_execution_plane_work_items(test_db_session, **{f"{scope}_id": uuid4()}) == []


@pytest.mark.parametrize("scope", ["project", "workflow"])
async def test_owner_deletion_schedules_captured_work_only_after_commit(
    test_db_session,
    test_execution,
    test_user,
    monkeypatch,
    scope,
):
    item_id = await _seed_activities(test_db_session, test_execution)
    work_item_ids = sorted([item_id, uuid5(test_execution.id, "http-node")])
    test_execution.status = ExecutionStatus.CANCELLED
    await test_db_session.commit()
    execution_id = test_execution.id
    committed = False
    original_commit = test_db_session.commit

    async def commit() -> None:
        nonlocal committed
        await original_commit()
        committed = True

    def schedule(ids) -> None:
        assert committed is True
        assert ids == work_item_ids

    scheduled = Mock(side_effect=schedule)
    monkeypatch.setattr(test_db_session, "commit", commit)
    monkeypatch.setattr(deletion, "schedule_work_item_deletion", scheduled)
    if scope == "project":
        service = ProjectService(test_db_session, test_user)
        monkeypatch.setattr(service, "_cleanup_temporal_schedules", AsyncMock())
        monkeypatch.setattr(service, "_cleanup_file_storage", AsyncMock())
        await service.delete_project(test_execution.project_id)
    else:
        service = WorkflowService(test_db_session, test_user)
        monkeypatch.setattr(service, "_schedule_trigger_deletion", Mock())
        await service.delete_workflow(test_execution.workflow_id)
    scheduled.assert_called_once_with(work_item_ids)
    assert (await test_db_session.exec(select(Execution.id).where(Execution.id == execution_id))).first() is None
    assert (
        await test_db_session.exec(select(ActivityExecution.id).where(ActivityExecution.id == item_id))
    ).first() is None


@pytest.mark.parametrize("scope", ["project", "workflow"])
async def test_failed_commit_does_not_schedule_ep_deletion(
    test_db_session, test_execution, test_user, monkeypatch, scope
):
    await _seed_activities(test_db_session, test_execution)
    test_execution.status = ExecutionStatus.CANCELLED
    await test_db_session.commit()
    scheduled = Mock()
    monkeypatch.setattr(deletion, "schedule_work_item_deletion", scheduled)
    monkeypatch.setattr(test_db_session, "commit", AsyncMock(side_effect=RuntimeError("commit failed")))
    if scope == "project":
        service = ProjectService(test_db_session, test_user)
        monkeypatch.setattr(service, "_cleanup_temporal_schedules", AsyncMock())
        monkeypatch.setattr(service, "_cleanup_file_storage", AsyncMock())
        operation = service.delete_project(test_execution.project_id)
    else:
        service = WorkflowService(test_db_session, test_user)
        operation = service.delete_workflow(test_execution.workflow_id)
    with pytest.raises(RuntimeError, match="commit failed"):
        await operation
    scheduled.assert_not_called()
    await test_db_session.rollback()
    # The fixture's teardown may commit after the test; restore its original method.
    monkeypatch.undo()
