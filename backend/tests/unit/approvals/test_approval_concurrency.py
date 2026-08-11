"""Tests for concurrent approval decision operations.

Verifies that optimistic and pessimistic locking prevent race conditions
when multiple users or batch operations attempt to decide the same approval simultaneously.

Concurrency tests use a dedicated session per actor (via ``test_session_factory``).
A shared AsyncSession cannot exercise true cross-transaction locking and previously
caused flaky failures / "This transaction is closed" errors under asyncio.gather.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete
from sqlmodel import col

from syntara.approvals.exceptions import ApprovalAlreadyDecidedError
from syntara.approvals.models import (
    ApprovalDecisionRequest,
    ApprovalRequest,
    ApprovalRequestRead,
    ApprovalRequestStatus,
    BatchApprovalDecision,
    BatchApprovalRequest,
    BatchApprovalResponse,
)
from syntara.approvals.services.approval_service import ApprovalService
from syntara.auth.passwords import hash_password
from syntara.authz.engine import AuthzResult
from syntara.authz.models.project import Project
from syntara.core.models import User

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture(autouse=True)
def _mock_evaluator_for_concurrency_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto-mock authz evaluator authorization for concurrency tests.

    Concurrency tests focus on locking behavior, not authorization,
    so we mock evaluator to always allow.
    """
    from unittest.mock import Mock

    mock_client = Mock()
    mock_client.__bool__ = Mock(return_value=True)

    async def mock_authorize(*args: object, **kwargs: object) -> AuthzResult:
        return AuthzResult(
            allowed=True,
            denied=False,
            matched_policy="approval.decide",
            denial_reason="",
            denied_by="",
            effective_policies=[],
        )

    monkeypatch.setattr(
        "syntara.authz.engine.authorize",
        mock_authorize,
    )

    # Patch ApprovalService.__init__ to inject mock_client when evaluator is None
    original_init = ApprovalService.__init__

    def patched_init(self, session, user, evaluator=None) -> None:
        if evaluator is None:
            evaluator = mock_client
        original_init(self, session, user, evaluator)

    monkeypatch.setattr(ApprovalService, "__init__", patched_init)


def _valid_workflow_context() -> dict[str, object]:
    """Return a valid workflow context structure for testing."""
    return {
        "workflow_id": str(uuid4()),
        "workflow_name": "Test Workflow",
        "inputs": {},
    }


def _valid_next_step() -> dict[str, str]:
    """Return a valid activity summary structure for testing."""
    return {
        "id": "test_step",
        "name": "Test Step",
        "type": "task",
    }


def _make_user(prefix: str = "user") -> User:
    """Build a unique User row for committed setup sessions."""
    suffix = uuid4().hex[:8]
    return User(
        username=f"{prefix}-{suffix}",
        email=f"{prefix}-{suffix}@example.com",
        first_name=prefix.title(),
        last_name="User",
        password_hash=hash_password("password123"),
        is_enabled=True,
    )


def _make_approval(project_id: UUID, node_id: str = "test_node") -> ApprovalRequest:
    """Build a pending ApprovalRequest for committed setup sessions."""
    return ApprovalRequest(
        execution_id=uuid4(),
        approval_node_id=node_id,
        project_id=project_id,
        name=f"Test Approval {node_id}",
        timeout_at=None,
        status=ApprovalRequestStatus.PENDING,
        workflow_context=_valid_workflow_context(),
        next_step_approved=_valid_next_step(),
        next_step_rejected=None,
    )


async def _cleanup_concurrency_rows(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    project_id: UUID,
    user_ids: list[UUID],
    approval_ids: list[UUID],
) -> None:
    """Delete committed concurrency-test rows (approvals → users → project)."""
    async with session_factory() as session:
        if approval_ids:
            await session.exec(delete(ApprovalRequest).where(col(ApprovalRequest.id).in_(approval_ids)))
        if user_ids:
            await session.exec(delete(User).where(col(User.id).in_(user_ids)))
        await session.exec(delete(Project).where(col(Project.id) == project_id))
        await session.commit()


@asynccontextmanager
async def _concurrency_data(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_count: int = 2,
    approval_count: int = 1,
) -> AsyncIterator[tuple[list[UUID], list[UUID]]]:
    """Commit project/users/approvals visible across sessions; delete them on exit.

    ``test_session_factory`` commits go to the real DB (no per-test rollback), so
    callers must clean up to preserve isolation for later tests in the session.
    """
    async with session_factory() as session:
        project = Project(name=f"concurrency-project-{uuid4().hex[:8]}", description="Concurrency test")
        session.add(project)
        await session.flush()

        users = [_make_user(f"actor{i}") for i in range(user_count)]
        session.add_all(users)
        await session.flush()

        approvals = [_make_approval(project.id, node_id=f"node_{i}") for i in range(approval_count)]
        session.add_all(approvals)
        await session.commit()

        project_id = project.id
        user_ids = [user.id for user in users]
        approval_ids = [approval.id for approval in approvals]

    try:
        yield user_ids, approval_ids
    finally:
        await _cleanup_concurrency_rows(
            session_factory,
            project_id=project_id,
            user_ids=user_ids,
            approval_ids=approval_ids,
        )


async def _decide_with_own_session(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: UUID,
    approval_id: UUID,
    decision: ApprovalDecisionRequest,
) -> ApprovalRequestRead:
    """Run decide() on a dedicated session (one session per concurrent actor)."""
    async with session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        service = ApprovalService(session, user)
        return await service.decide(approval_id, decision)


async def _batch_decide_with_own_session(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: UUID,
    decisions: list[BatchApprovalDecision],
) -> BatchApprovalResponse:
    """Run batch_decide() on a dedicated session."""
    async with session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        service = ApprovalService(session, user)
        return await service.batch_decide(BatchApprovalRequest(decisions=decisions))


@pytest.fixture
def mock_workflow_client():
    """Mock the workflow client to avoid HTTP calls in unit tests."""
    with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.send_approval_signal = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client
        yield mock_client


@pytest.mark.asyncio
async def test_concurrent_decisions_only_one_succeeds(
    test_session_factory: async_sessionmaker[AsyncSession],
    mock_workflow_client: AsyncMock,
) -> None:
    """Test that when two users decide the same approval simultaneously, only one succeeds.

    This verifies the optimistic locking implementation (WHERE status=PENDING)
    prevents double-decision race conditions.
    """
    async with _concurrency_data(test_session_factory, user_count=2, approval_count=1) as (
        user_ids,
        approval_ids,
    ):
        approval_id = approval_ids[0]

        results = await asyncio.gather(
            _decide_with_own_session(
                test_session_factory,
                user_ids[0],
                approval_id,
                ApprovalDecisionRequest(status="approved", note="Actor 0 approves"),
            ),
            _decide_with_own_session(
                test_session_factory,
                user_ids[1],
                approval_id,
                ApprovalDecisionRequest(status="approved", note="Actor 1 approves"),
            ),
            return_exceptions=True,
        )

        success_count = sum(1 for r in results if not isinstance(r, Exception))
        error_count = sum(1 for r in results if isinstance(r, ApprovalAlreadyDecidedError))

        assert success_count == 1, f"Exactly one decision should succeed; got {results!r}"
        assert error_count == 1, f"Exactly one decision should fail with AlreadyDecided; got {results!r}"

        async with test_session_factory() as session:
            approval = await session.get(ApprovalRequest, approval_id)
            assert approval is not None
            assert approval.status in (ApprovalRequestStatus.APPROVED, ApprovalRequestStatus.REJECTED)
            assert approval.decided_by is not None
            assert approval.decided_at is not None


@pytest.mark.asyncio
async def test_concurrent_decision_and_list_no_deadlock(
    test_db_session: AsyncSession,
    admin_user: User,
    mock_workflow_client: AsyncMock,
    test_project_id: UUID,
) -> None:
    """Test that concurrent decision and list operations don't deadlock.

    Decision uses optimistic locking (no row lock), list uses SELECT (no lock),
    so they should not block each other.
    """
    # Create multiple approval requests
    approvals = [
        ApprovalRequest(
            execution_id=uuid4(),
            approval_node_id=f"node_{i}",
            project_id=test_project_id,
            name=f"Test Approval {i}",
            timeout_at=None,
            status=ApprovalRequestStatus.PENDING,
            workflow_context=_valid_workflow_context(),
            next_step_approved=_valid_next_step(),
            next_step_rejected=None,
        )
        for i in range(5)
    ]
    for approval in approvals:
        test_db_session.add(approval)
    await test_db_session.commit()

    for approval in approvals:
        await test_db_session.refresh(approval)

    service = ApprovalService(test_db_session, admin_user)
    decision = ApprovalDecisionRequest(status="approved", note="Concurrent test")

    # Spawn concurrent operations: decide first approval + list all approvals
    results = await asyncio.gather(
        service.decide(approvals[0].id, decision),
        service.list(limit=10),
        return_exceptions=True,
    )

    # Both operations should succeed without deadlock or timeout
    assert len(results) == 2
    assert not isinstance(results[0], Exception), f"Decision failed: {results[0]}"
    assert not isinstance(results[1], Exception), f"List failed: {results[1]}"


@pytest.mark.asyncio
async def test_batch_decision_locks_prevent_concurrent_single_decision(
    test_session_factory: async_sessionmaker[AsyncSession],
    mock_workflow_client: AsyncMock,
) -> None:
    """Test that batch FOR UPDATE and single decide contend safely across sessions.

    Exactly one path should apply the decision; the loser either raises
    ApprovalAlreadyDecidedError (single decide) or reports failure in the batch result.
    """
    async with _concurrency_data(test_session_factory, user_count=2, approval_count=1) as (
        user_ids,
        approval_ids,
    ):
        approval_id = approval_ids[0]

        batch_decisions = [BatchApprovalDecision(approval_id=approval_id, status="approved", note="Batch approve")]
        single_decision = ApprovalDecisionRequest(status="approved", note="Single approve")

        results = await asyncio.gather(
            _batch_decide_with_own_session(test_session_factory, user_ids[0], batch_decisions),
            _decide_with_own_session(test_session_factory, user_ids[1], approval_id, single_decision),
            return_exceptions=True,
        )
        batch_result, single_result = results

        assert not isinstance(batch_result, Exception), f"Batch failed unexpectedly: {batch_result}"

        batch_won = isinstance(batch_result, BatchApprovalResponse) and batch_result.total_success == 1
        single_won = not isinstance(single_result, Exception)
        single_lost = isinstance(single_result, ApprovalAlreadyDecidedError)

        assert batch_won ^ single_won, f"Exactly one path should decide the approval; got {results!r}"
        if single_won:
            assert not batch_won
        else:
            assert single_lost, f"Losing single decide should raise AlreadyDecided; got {single_result!r}"

        async with test_session_factory() as session:
            approval = await session.get(ApprovalRequest, approval_id)
            assert approval is not None
            assert approval.status == ApprovalRequestStatus.APPROVED
            assert approval.decided_by is not None


@pytest.mark.asyncio
async def test_batch_decision_with_duplicate_ids_processes_once(
    test_db_session: AsyncSession,
    admin_user: User,
    mock_workflow_client: AsyncMock,
    test_project_id: UUID,
) -> None:
    """Test that batch decision with duplicate approval IDs only processes each approval once.

    Batch operation should deduplicate IDs before processing, or handle duplicates gracefully.
    """
    # Create two approval requests
    approval1 = ApprovalRequest(
        execution_id=uuid4(),
        approval_node_id="node_1",
        project_id=test_project_id,
        name="Test Approval 1",
        timeout_at=None,
        status=ApprovalRequestStatus.PENDING,
        workflow_context=_valid_workflow_context(),
        next_step_approved=_valid_next_step(),
        next_step_rejected=None,
    )
    approval2 = ApprovalRequest(
        execution_id=uuid4(),
        approval_node_id="node_2",
        project_id=test_project_id,
        name="Test Approval 2",
        timeout_at=None,
        status=ApprovalRequestStatus.PENDING,
        workflow_context=_valid_workflow_context(),
        next_step_approved=_valid_next_step(),
        next_step_rejected=None,
    )
    test_db_session.add(approval1)
    test_db_session.add(approval2)
    await test_db_session.commit()
    await test_db_session.refresh(approval1)
    await test_db_session.refresh(approval2)

    service = ApprovalService(test_db_session, admin_user)

    # Create batch with duplicate IDs and conflicting decisions
    batch_decisions = [
        BatchApprovalDecision(approval_id=approval1.id, status="approved", note="First decision"),
        BatchApprovalDecision(approval_id=approval1.id, status="rejected", note="Duplicate decision"),
        BatchApprovalDecision(approval_id=approval2.id, status="approved", note="Second approval"),
    ]

    response = await service.batch_decide(BatchApprovalRequest(decisions=batch_decisions))

    # Both approvals should be processed (duplicates handled)
    assert len(response.results) == 3

    # Verify approval1 was decided (first decision wins)
    await test_db_session.refresh(approval1)
    assert approval1.status in (ApprovalRequestStatus.APPROVED, ApprovalRequestStatus.REJECTED)

    # Verify approval2 was decided
    await test_db_session.refresh(approval2)
    assert approval2.status == ApprovalRequestStatus.APPROVED


@pytest.mark.asyncio
async def test_concurrent_batch_decisions_no_overlap(
    test_session_factory: async_sessionmaker[AsyncSession],
    mock_workflow_client: AsyncMock,
) -> None:
    """Test that concurrent batch decisions on non-overlapping approvals succeed.

    Two batches with completely different approval sets should not conflict.
    """
    async with _concurrency_data(test_session_factory, user_count=2, approval_count=4) as (
        user_ids,
        approval_ids,
    ):
        batch1 = [
            BatchApprovalDecision(approval_id=approval_ids[0], status="approved", note="Batch 1"),
            BatchApprovalDecision(approval_id=approval_ids[1], status="approved", note="Batch 1"),
        ]
        batch2 = [
            BatchApprovalDecision(approval_id=approval_ids[2], status="rejected", note="Batch 2"),
            BatchApprovalDecision(approval_id=approval_ids[3], status="rejected", note="Batch 2"),
        ]

        results = await asyncio.gather(
            _batch_decide_with_own_session(test_session_factory, user_ids[0], batch1),
            _batch_decide_with_own_session(test_session_factory, user_ids[1], batch2),
            return_exceptions=True,
        )

        assert len(results) == 2
        assert isinstance(results[0], BatchApprovalResponse), f"Batch 1 failed: {results[0]}"
        assert isinstance(results[1], BatchApprovalResponse), f"Batch 2 failed: {results[1]}"
        assert results[0].total_success == 2
        assert results[1].total_success == 2

        async with test_session_factory() as session:
            for approval_id in approval_ids:
                approval = await session.get(ApprovalRequest, approval_id)
                assert approval is not None
                assert approval.status in (ApprovalRequestStatus.APPROVED, ApprovalRequestStatus.REJECTED)


@pytest.mark.asyncio
async def test_concurrent_batch_decisions_with_overlap(
    test_session_factory: async_sessionmaker[AsyncSession],
    mock_workflow_client: AsyncMock,
) -> None:
    """Test that concurrent batch decisions on overlapping approvals handle conflicts gracefully.

    Two batches trying to decide the same approval should result in one batch
    succeeding for the overlapping approval and the other failing for that specific approval.
    """
    async with _concurrency_data(test_session_factory, user_count=2, approval_count=3) as (
        user_ids,
        approval_ids,
    ):
        batch1 = [
            BatchApprovalDecision(approval_id=approval_ids[0], status="approved", note="Batch 1"),
            BatchApprovalDecision(approval_id=approval_ids[1], status="approved", note="Batch 1"),
        ]
        batch2 = [
            BatchApprovalDecision(approval_id=approval_ids[1], status="rejected", note="Batch 2"),
            BatchApprovalDecision(approval_id=approval_ids[2], status="rejected", note="Batch 2"),
        ]

        results = await asyncio.gather(
            _batch_decide_with_own_session(test_session_factory, user_ids[0], batch1),
            _batch_decide_with_own_session(test_session_factory, user_ids[1], batch2),
            return_exceptions=True,
        )

        assert len(results) == 2
        assert isinstance(results[0], BatchApprovalResponse), f"Batch 1 failed: {results[0]}"
        assert isinstance(results[1], BatchApprovalResponse), f"Batch 2 failed: {results[1]}"
        batch1_result = results[0]
        batch2_result = results[1]

        # Winner of the overlap claims both of its decisions (exclusive + overlap) =>
        # total_success == 2; the other batch keeps only its exclusive => total_success == 1.
        overlap_won_by_batch1 = batch1_result.total_success == 2
        overlap_won_by_batch2 = batch2_result.total_success == 2
        assert overlap_won_by_batch1 ^ overlap_won_by_batch2, (
            f"Exactly one batch should win the overlapping approval; got {results!r}"
        )
        assert batch1_result.total_success + batch2_result.total_success == 3, (
            f"Expected 2 exclusive + 1 overlap successes; got {results!r}"
        )

        # Non-overlapping approvals always succeed in their owning batch
        assert any(item.approval_id == approval_ids[0] and item.success for item in batch1_result.results)
        assert any(item.approval_id == approval_ids[2] and item.success for item in batch2_result.results)

        overlap_successes = sum(
            1
            for response in (batch1_result, batch2_result)
            for item in response.results
            if item.approval_id == approval_ids[1] and item.success
        )
        assert overlap_successes == 1, f"Overlap approval should be decided by exactly one batch; got {results!r}"

        async with test_session_factory() as session:
            for approval_id in approval_ids:
                approval = await session.get(ApprovalRequest, approval_id)
                assert approval is not None
                assert approval.status in (ApprovalRequestStatus.APPROVED, ApprovalRequestStatus.REJECTED)
