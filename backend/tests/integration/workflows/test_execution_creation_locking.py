"""Two-connection lock tests for the create-vs-delete race (AAP-87750, Part 1).

Execution creation takes ``FOR KEY SHARE`` on the workflow row *before* starting
Temporal and holds it until the execution row commits.  Workflow deletion takes
``FOR UPDATE`` on the same row.  Those conflict, which is what stops a run from
being started into a workflow that is being deleted.

These tests drive two real database connections concurrently and assert the lock
actually blocks.  Without them, deleting ``.with_for_update(...)`` from the
creation paths breaks nothing and the whole correctness argument is untested.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlmodel import select, text
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.workflows.models import Workflow
from tests.helpers.workflow import create_minimal_workflow_definition

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from syntara.core.models import User

pytestmark = pytest.mark.asyncio

# Long enough that a non-blocking query finishes well inside it, short enough that
# a genuinely blocked one is still waiting when we check.
_SETTLE_SECONDS = 0.75


async def _make_workflow(session: AsyncSession, project_id: UUID, user_id: UUID) -> UUID:
    workflow_id = uuid4()
    session.add(
        Workflow(
            id=workflow_id,
            name=f"lock-test-{uuid4().hex[:8]}",
            project_id=project_id,
            created_by=user_id,
            current_version=1,
            is_enabled=False,
            workflow_definition=create_minimal_workflow_definition(name="lock-test"),
        )
    )
    await session.commit()
    return workflow_id


async def _key_share(session: AsyncSession, workflow_id: UUID) -> None:
    """Take the lock execution creation takes."""
    await session.exec(select(Workflow).where(Workflow.id == workflow_id).with_for_update(read=True, key_share=True))


async def _for_update(session: AsyncSession, workflow_id: UUID) -> None:
    """Take the lock workflow deletion takes."""
    await session.exec(select(Workflow).where(Workflow.id == workflow_id).with_for_update())


async def test_for_update_blocks_while_key_share_is_held(
    test_db_engine: AsyncEngine,
    test_db_session: AsyncSession,
    test_project_id: UUID,
    test_user: User,
) -> None:
    """The deleter must wait while a creation holds FOR KEY SHARE.

    This is the property the fix depends on: a run cannot be started into a
    workflow whose delete is already in flight, and vice versa.
    """
    workflow_id = await _make_workflow(test_db_session, test_project_id, test_user.id)

    async with (
        AsyncSession(test_db_engine, expire_on_commit=False) as creator,
        AsyncSession(test_db_engine, expire_on_commit=False) as deleter,
    ):
        # Creator holds FOR KEY SHARE (stands in for the window across the
        # Temporal start_workflow call).
        await _key_share(creator, workflow_id)

        deleter_task = asyncio.create_task(_for_update(deleter, workflow_id))
        done, _pending = await asyncio.wait({deleter_task}, timeout=_SETTLE_SECONDS)

        assert not done, "FOR UPDATE did not block — the creation lock is not being taken"

        # Releasing the creator lets the deleter through.
        await creator.rollback()
        await asyncio.wait_for(deleter_task, timeout=10)
        await deleter.rollback()


async def test_two_creations_do_not_block_each_other(
    test_db_engine: AsyncEngine,
    test_db_session: AsyncSession,
    test_project_id: UUID,
    test_user: User,
) -> None:
    """Share locks must not serialise concurrent runs of the same workflow.

    If this ever fails, the lock is too strong and every execution start on a busy
    workflow queues behind every other one.
    """
    workflow_id = await _make_workflow(test_db_session, test_project_id, test_user.id)

    async with (
        AsyncSession(test_db_engine, expire_on_commit=False) as first,
        AsyncSession(test_db_engine, expire_on_commit=False) as second,
    ):
        await _key_share(first, workflow_id)
        await asyncio.wait_for(_key_share(second, workflow_id), timeout=10)
        await first.rollback()
        await second.rollback()


async def test_key_share_does_not_block_ordinary_workflow_updates(
    test_db_engine: AsyncEngine,
    test_db_session: AsyncSession,
    test_project_id: UUID,
    test_user: User,
) -> None:
    """KEY SHARE is the weakest sufficient lock.

    A non-key UPDATE takes FOR NO KEY UPDATE, which does not conflict with it — so
    renaming a workflow while a run is starting must not block.  Using plain SHARE
    instead would break this.
    """
    workflow_id = await _make_workflow(test_db_session, test_project_id, test_user.id)

    async with (
        AsyncSession(test_db_engine, expire_on_commit=False) as creator,
        AsyncSession(test_db_engine, expire_on_commit=False) as updater,
    ):
        await _key_share(creator, workflow_id)

        async def rename() -> None:
            await updater.execute(
                text("UPDATE workflows SET description = :d WHERE id = :id").bindparams(
                    d="renamed while a run was starting", id=workflow_id
                )
            )

        await asyncio.wait_for(rename(), timeout=10)
        await updater.rollback()
        await creator.rollback()


async def test_deleter_lock_is_released_when_its_transaction_ends(
    test_db_engine: AsyncEngine,
    test_db_session: AsyncSession,
    test_project_id: UUID,
    test_user: User,
) -> None:
    """A conflict-aborted delete must not leave creations wedged.

    delete_workflow raises WorkflowDeleteConflictError without rolling back
    explicitly, relying on session teardown; this asserts that assumption.
    """
    workflow_id = await _make_workflow(test_db_session, test_project_id, test_user.id)

    async with AsyncSession(test_db_engine, expire_on_commit=False) as deleter:
        await _for_update(deleter, workflow_id)

    # Teardown ended the transaction, so a creation can proceed immediately.
    async with AsyncSession(test_db_engine, expire_on_commit=False) as creator:
        await asyncio.wait_for(_key_share(creator, workflow_id), timeout=10)
        await creator.rollback()


async def test_real_create_execution_blocks_while_a_delete_holds_the_row(
    test_db_engine: AsyncEngine,
    test_db_session: AsyncSession,
    test_project_id: UUID,
    test_user: User,
) -> None:
    """Drive the production path, not just Postgres semantics.

    ``ExecutionService.create_execution`` must take a conflicting lock on the
    workflow row *before* it reaches Temporal.  Holding FOR UPDATE elsewhere — what
    ``delete_workflow`` does — must therefore stall it.

    This is the test that fails if ``.with_for_update(read=True, key_share=True)``
    is removed from the creation query: without it the SELECT sails past the lock
    and the call proceeds.
    """
    from unittest.mock import AsyncMock, Mock

    from syntara.workflows.models.workflow_version import WorkflowVersion
    from syntara.workflows.services.execution_service import ExecutionService
    from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService

    workflow_id, version_id = uuid4(), uuid4()
    definition = create_minimal_workflow_definition(name="lock-prod-path")
    test_db_session.add(
        Workflow(
            id=workflow_id,
            name=f"lock-prod-{uuid4().hex[:8]}",
            project_id=test_project_id,
            created_by=test_user.id,
            current_version=1,
            is_enabled=False,
            workflow_definition=definition,
        )
    )
    await test_db_session.flush()
    test_db_session.add(
        WorkflowVersion(
            id=version_id,
            workflow_id=workflow_id,
            version=1,
            schema_version="2.0.0",
            created_by=test_user.id,
            workflow_definition=definition,
        )
    )
    await test_db_session.commit()

    temporal = Mock(spec=TemporalExecutionService)
    started = asyncio.Event()

    async def start_workflow(**_kwargs: object) -> Mock:
        started.set()
        result = Mock()
        result.temporal_workflow_id = f"tw-{uuid4().hex[:8]}"
        result.temporal_run_id = "run-1"
        result.execution_id = str(uuid4())
        return result

    temporal.start_workflow = AsyncMock(side_effect=start_workflow)

    async with (
        AsyncSession(test_db_engine, expire_on_commit=False) as deleter,
        AsyncSession(test_db_engine, expire_on_commit=False) as creator_session,
    ):
        # Stand in for delete_workflow's phase-3 lock.
        await _for_update(deleter, workflow_id)

        service = ExecutionService(session=creator_session, user=test_user, temporal_service=temporal)
        create_task = asyncio.create_task(
            service.create_execution(
                workflow_id=workflow_id,
                input_data={},
                trigger_node_id="trigger_manual",
            )
        )
        done, _pending = await asyncio.wait({create_task}, timeout=_SETTLE_SECONDS)

        assert not done, "create_execution did not block — its workflow lookup is not taking the row lock"
        assert not started.is_set(), "Temporal was started before the lock was acquired"

        # Release the deleter; the creation should then get through.
        await deleter.rollback()
        await asyncio.wait_for(create_task, timeout=20)
        assert started.is_set()
