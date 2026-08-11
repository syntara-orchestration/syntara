"""Tests for approval creation error handling.

Verifies proper exception handling for race conditions (TOCTOU) and
foreign key constraint violations during approval creation.
"""

from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.approvals.exceptions import ApprovalAlreadyRequestedError
from syntara.approvals.models import ActivitySummary, ApprovalCreateRequest, WorkflowContext
from syntara.approvals.services.approval_service import ApprovalService
from syntara.core.models import User


def _create_test_approval_request(
    execution_id: UUID,
    approval_node_id: str,
    approver_user_ids: list[UUID] | None = None,
    approver_group_ids: list[UUID] | None = None,
    project_id: UUID | None = None,
) -> ApprovalCreateRequest:
    """Helper to create a valid ApprovalCreateRequest for testing."""
    workflow_context = WorkflowContext(
        workflow_id=uuid4(),
        workflow_name="Test Workflow",
        inputs={},
    )
    next_step_approved = ActivitySummary(
        id="test_step",
        name="Test Step",
        type="task",
    )
    return ApprovalCreateRequest(
        execution_id=execution_id,
        approval_node_id=approval_node_id,
        name="Test Approval",
        timeout_at=None,
        next_step_approved=next_step_approved,
        next_step_rejected=None,
        workflow_context=workflow_context,
        approver_user_ids=approver_user_ids or [],
        approver_group_ids=approver_group_ids or [],
        project_id=project_id or uuid4(),
    )


@pytest.mark.asyncio
@patch.object(ApprovalService, "_validate_execution_reference", new_callable=AsyncMock)
async def test_concurrent_approval_creation_race_condition(
    mock_validate: AsyncMock,
    test_db_session: AsyncSession,
    admin_user: User,
    test_project_id: UUID,
) -> None:
    """Test that duplicate approval creation is prevented by unique constraint.

    The unique constraint on (execution_id, approval_node_id) prevents duplicate
    approvals. When a duplicate is attempted, IntegrityError is converted to
    ApprovalAlreadyRequestedError.

    Note: asyncio.gather with a shared session may serialize the operations,
    so we test sequential duplicate creation instead of true concurrency.
    """
    execution_id = uuid4()
    approval_node_id = "test_node"

    service = ApprovalService(test_db_session, admin_user)

    request = _create_test_approval_request(execution_id, approval_node_id, project_id=test_project_id)

    # Create first approval - should succeed
    first_result = await service.create(request)
    assert first_result is not None, "First approval creation should succeed"

    # Attempt to create duplicate - should fail with ApprovalAlreadyRequestedError
    with pytest.raises(ApprovalAlreadyRequestedError) as exc_info:
        await service.create(request)

    # Verify error contains correct execution_id and approval_node_id
    error = exc_info.value
    assert error.execution_id == execution_id
    assert error.approval_node_id == approval_node_id


@pytest.mark.asyncio
@patch.object(ApprovalService, "_validate_execution_reference", new_callable=AsyncMock)
async def test_approval_creation_with_invalid_user_id(
    mock_validate: AsyncMock,
    test_db_session: AsyncSession,
    admin_user: User,
    test_project_id: UUID,
) -> None:
    """Test that approval creation with invalid user_id raises ValueError (400).

    Invalid approver UUIDs should raise ValueError with helpful message,
    not IntegrityError (500).
    """
    execution_id = uuid4()
    invalid_user_id = uuid4()  # UUID that doesn't exist in database

    service = ApprovalService(test_db_session, admin_user)

    request = _create_test_approval_request(
        execution_id,
        "test_node",
        approver_user_ids=[invalid_user_id],
        project_id=test_project_id,
    )

    # Should raise ValueError (not IntegrityError)
    with pytest.raises(ValueError) as exc_info:
        await service.create(request)

    # Error message should mention user IDs and be helpful
    error_msg = str(exc_info.value)
    assert "user" in error_msg.lower()
    assert str(invalid_user_id) in error_msg


@pytest.mark.asyncio
@patch.object(ApprovalService, "_validate_execution_reference", new_callable=AsyncMock)
async def test_approval_creation_with_invalid_group_id(
    mock_validate: AsyncMock,
    test_db_session: AsyncSession,
    admin_user: User,
    test_project_id: UUID,
) -> None:
    """Test that approval creation with invalid group_id raises ValueError (400).

    Invalid approver group UUIDs should raise ValueError with helpful message,
    not IntegrityError (500).
    """
    execution_id = uuid4()
    invalid_group_id = uuid4()  # UUID that doesn't exist in database

    service = ApprovalService(test_db_session, admin_user)

    request = _create_test_approval_request(
        execution_id,
        "test_node",
        approver_group_ids=[invalid_group_id],
        project_id=test_project_id,
    )

    # Should raise ValueError (not IntegrityError)
    with pytest.raises(ValueError) as exc_info:
        await service.create(request)

    # Error message should mention group IDs and be helpful
    error_msg = str(exc_info.value)
    assert "group" in error_msg.lower()
    assert str(invalid_group_id) in error_msg


@pytest.mark.asyncio
@patch.object(ApprovalService, "_validate_execution_reference", new_callable=AsyncMock)
async def test_approval_creation_with_mixed_valid_invalid_approvers(
    mock_validate: AsyncMock,
    test_db_session: AsyncSession,
    admin_user: User,
    user_factory: Callable[..., Awaitable[User]],
    test_project_id: UUID,
) -> None:
    """Test that approval creation fails if ANY approver UUID is invalid.

    Even if some approver UUIDs are valid, a single invalid UUID should
    fail the entire transaction (atomicity guarantee).
    """
    execution_id = uuid4()
    valid_user = await user_factory()
    valid_user_id = valid_user.id
    invalid_user_id = uuid4()  # Doesn't exist

    service = ApprovalService(test_db_session, admin_user)

    request = _create_test_approval_request(
        execution_id,
        "test_node",
        approver_user_ids=[valid_user_id, invalid_user_id],
        project_id=test_project_id,
    )

    # Should raise ValueError due to invalid UUID
    with pytest.raises(ValueError):
        await service.create(request)

    # Verify approval was NOT created (transaction rolled back)
    approval = await service._get_approval_request(execution_id, "test_node")
    assert approval is None, "Approval should not exist due to transaction rollback"


@pytest.mark.asyncio
@patch.object(ApprovalService, "_validate_execution_reference", new_callable=AsyncMock)
async def test_approval_already_requested_error_message(
    mock_validate: AsyncMock,
    test_db_session: AsyncSession,
    admin_user: User,
    test_project_id: UUID,
) -> None:
    """Test that attempting to create duplicate approval raises clear error."""
    execution_id = uuid4()
    approval_node_id = "test_node"

    service = ApprovalService(test_db_session, admin_user)

    request = _create_test_approval_request(execution_id, approval_node_id, project_id=test_project_id)

    # Create first approval
    await service.create(request)

    # Attempt to create duplicate
    with pytest.raises(ApprovalAlreadyRequestedError) as exc_info:
        await service.create(request)

    # Verify error contains execution_id and approval_node_id
    error = exc_info.value
    assert error.execution_id == execution_id
    assert error.approval_node_id == approval_node_id
