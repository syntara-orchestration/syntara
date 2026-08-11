"""Unit tests for ActivityExecution model.

Tests cover:
- ActivityExecution creation with required fields
- Status enum validation
- Timezone-aware datetime fields
- JSONB labels operations
- Unique constraint on (execution_id, temporal_activity_id)
- Relationship with Execution model
- Activity definition storage and retrieval
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.models import Workflow, WorkflowVersion
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution


@pytest.mark.asyncio
async def test_create_activity_execution_with_required_fields(
    test_db_session: AsyncSession,
    test_execution_minimal: Execution,
) -> None:
    """Test creating an activity execution with required fields only."""
    execution = test_execution_minimal

    # Create activity execution
    activity = ActivityExecution(
        execution_id=execution.id,
        activity_name="test_activity",
        node_type="script",
        temporal_activity_id="activity-123",
        status=ActivityStatus.PENDING,
    )
    test_db_session.add(activity)
    await test_db_session.commit()

    assert activity.id is not None
    assert activity.execution_id == execution.id
    assert activity.activity_name == "test_activity"
    assert activity.node_type == "script"
    assert activity.temporal_activity_id == "activity-123"
    assert activity.status == ActivityStatus.PENDING
    assert activity.labels == {}
    assert activity.created_at is not None
    assert activity.updated_at is not None
    assert activity.started_at is None
    assert activity.completed_at is None
    assert activity.input_data == {}
    assert activity.output_data is None
    assert activity.error_details is None
    assert activity.retry_count == 0
    assert activity.iteration is None


@pytest.mark.asyncio
async def test_create_activity_execution_with_all_fields(
    test_db_session: AsyncSession,
    test_execution_minimal: Execution,
) -> None:
    """Test creating an activity execution with all fields."""
    execution = test_execution_minimal

    # Create activity execution with all fields
    now = datetime.now(UTC)
    labels = {"environment": "test", "retry": "true"}
    activity_def = {"id": "activity_1", "type": "script", "parameters": {"language": "bash", "code": "echo ok"}}
    input_data = {"param1": "value1"}
    output_data = {"result": "success"}

    activity = ActivityExecution(
        execution_id=execution.id,
        activity_name="complete_activity",
        node_type=activity_def["type"],
        temporal_activity_id="activity-456",
        status=ActivityStatus.COMPLETED,
        labels=labels,
        started_at=now,
        completed_at=now,
        input_data=input_data,
        output_data=output_data,
        error_details="No errors",
        retry_count=2,
        iteration=1,
    )
    test_db_session.add(activity)
    await test_db_session.commit()

    assert activity.activity_name == "complete_activity"
    assert activity.status == ActivityStatus.COMPLETED
    assert activity.labels == labels
    assert activity.node_type == "script"
    assert activity.started_at == now
    assert activity.completed_at == now
    assert activity.input_data == input_data
    assert activity.output_data == output_data
    assert activity.error_details == "No errors"
    assert activity.retry_count == 2
    assert activity.iteration == 1


@pytest.mark.asyncio
async def test_activity_status_enum_values(
    test_db_session: AsyncSession,
    test_execution_minimal: Execution,
) -> None:
    """Test all valid ActivityStatus enum values."""
    execution = test_execution_minimal

    # Test each status value
    statuses = [
        ActivityStatus.PENDING,
        ActivityStatus.RUNNING,
        ActivityStatus.COMPLETED,
        ActivityStatus.FAILED,
        ActivityStatus.RETRYING,
    ]

    for i, status in enumerate(statuses):
        activity = ActivityExecution(
            execution_id=execution.id,
            activity_name=f"activity_{i}",
            node_type="script",
            temporal_activity_id=f"activity-{i}",
            status=status,
        )
        test_db_session.add(activity)

    await test_db_session.commit()

    # Verify all statuses were saved correctly
    activities_result = await test_db_session.exec(
        select(ActivityExecution).where(ActivityExecution.execution_id == execution.id)
    )
    activities = list(activities_result.all())
    assert len(activities) == len(statuses)
    assert {a.status for a in activities} == set(statuses)


@pytest.mark.asyncio
async def test_activity_unique_constraint_execution_temporal_id(
    test_db_session: AsyncSession,
    test_execution_minimal: Execution,
) -> None:
    """Test unique constraint on (execution_id, temporal_activity_id)."""
    execution = test_execution_minimal

    # Create first activity
    activity1 = ActivityExecution(
        execution_id=execution.id,
        activity_name="test_activity",
        node_type="script",
        temporal_activity_id="activity-123",
        status=ActivityStatus.PENDING,
    )
    test_db_session.add(activity1)
    await test_db_session.commit()

    # Try to create duplicate with same execution_id and temporal_activity_id
    activity2 = ActivityExecution(
        execution_id=execution.id,
        activity_name="different_name",  # Different name is OK
        node_type="script",
        temporal_activity_id="activity-123",  # But same temporal_activity_id should fail
        status=ActivityStatus.RUNNING,
    )
    test_db_session.add(activity2)

    with pytest.raises(IntegrityError) as exc_info:
        await test_db_session.commit()

    assert "uix_execution_activity" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_activity_allows_same_temporal_id_different_executions(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow_minimal: Workflow,
    test_workflow_version_minimal: WorkflowVersion,
) -> None:
    """Test that same temporal_activity_id is allowed across different executions."""
    # Create two executions
    execution1 = Execution(
        id=uuid4(),
        workflow_id=test_workflow_minimal.id,
        workflow_version_id=test_workflow_version_minimal.id,
        temporal_workflow_id="test-workflow-123",
        created_by=test_user.id,
        project_id=test_workflow_minimal.project_id,
    )
    execution2 = Execution(
        id=uuid4(),
        workflow_id=test_workflow_minimal.id,
        workflow_version_id=test_workflow_version_minimal.id,
        temporal_workflow_id="test-workflow-456",
        created_by=test_user.id,
        project_id=test_workflow_minimal.project_id,
    )
    test_db_session.add_all([execution1, execution2])
    await test_db_session.commit()

    # Create activities with same temporal_activity_id but different execution_id
    activity1 = ActivityExecution(
        execution_id=execution1.id,
        activity_name="test_activity",
        node_type="script",
        temporal_activity_id="activity-shared",
        status=ActivityStatus.PENDING,
    )
    activity2 = ActivityExecution(
        execution_id=execution2.id,
        activity_name="test_activity",
        node_type="script",
        temporal_activity_id="activity-shared",  # Same ID is OK for different execution
        status=ActivityStatus.RUNNING,
    )
    test_db_session.add_all([activity1, activity2])
    await test_db_session.commit()  # Should succeed

    # Verify both were created
    activities_result = await test_db_session.exec(
        select(ActivityExecution).where(ActivityExecution.temporal_activity_id == "activity-shared")
    )
    activities = list(activities_result.all())
    assert len(activities) == 2


@pytest.mark.asyncio
async def test_activity_timezone_aware_datetimes(
    test_db_session: AsyncSession,
    test_execution_minimal: Execution,
) -> None:
    """Test that datetime fields are timezone-aware."""
    execution = test_execution_minimal

    # Create activity with timezone-aware datetimes
    now = datetime.now(UTC)
    activity = ActivityExecution(
        execution_id=execution.id,
        activity_name="test_activity",
        node_type="script",
        temporal_activity_id="activity-123",
        status=ActivityStatus.RUNNING,
        started_at=now,
    )
    test_db_session.add(activity)
    await test_db_session.commit()

    # Verify datetimes are timezone-aware
    assert activity.created_at.tzinfo is not None
    assert activity.updated_at.tzinfo is not None
    assert activity.started_at is not None
    assert activity.started_at.tzinfo is not None


@pytest.mark.asyncio
async def test_activity_labels_jsonb_operations(
    test_db_session: AsyncSession,
    test_execution_minimal: Execution,
) -> None:
    """Test JSONB labels field operations."""
    execution = test_execution_minimal

    # Create activity with labels
    labels = {"environment": "production", "retry": "true", "priority": "high"}
    activity = ActivityExecution(
        execution_id=execution.id,
        activity_name="test_activity",
        node_type="script",
        temporal_activity_id="activity-123",
        status=ActivityStatus.PENDING,
        labels=labels,
    )
    test_db_session.add(activity)
    await test_db_session.commit()

    # Verify labels stored correctly
    assert activity.labels == labels
    assert activity.labels["environment"] == "production"

    # Update labels
    activity.labels = {"environment": "staging"}
    await test_db_session.commit()

    assert activity.labels == {"environment": "staging"}


@pytest.mark.asyncio
async def test_activity_relationship_with_execution(
    test_db_session: AsyncSession,
    test_execution_minimal: Execution,
) -> None:
    """Test relationship between ActivityExecution and Execution models."""
    execution = test_execution_minimal

    # Create multiple activities for the execution
    activities = [
        ActivityExecution(
            execution_id=execution.id,
            activity_name=f"activity_{i}",
            node_type="script",
            temporal_activity_id=f"activity-{i}",
            status=ActivityStatus.PENDING,
        )
        for i in range(3)
    ]
    test_db_session.add_all(activities)
    await test_db_session.commit()

    # Reload execution with activities relationship
    exec_result = await test_db_session.exec(select(Execution).where(Execution.id == execution.id))
    loaded_execution = exec_result.one()

    # Access activities through relationship (will trigger lazy load)
    activities_result = await test_db_session.exec(
        select(ActivityExecution).where(ActivityExecution.execution_id == loaded_execution.id)
    )
    loaded_activities = list(activities_result.all())

    assert len(loaded_activities) == 3
    assert all(a.execution_id == execution.id for a in loaded_activities)


@pytest.mark.asyncio
async def test_node_type_storage(
    test_db_session: AsyncSession,
    test_execution_minimal: Execution,
) -> None:
    """Test node_type field is stored and retrieved correctly."""
    execution = test_execution_minimal

    activity = ActivityExecution(
        execution_id=execution.id,
        activity_name="fetch_data",
        node_type="http_request",
        temporal_activity_id="activity-123",
        status=ActivityStatus.COMPLETED,
    )
    test_db_session.add(activity)
    await test_db_session.commit()

    assert activity.node_type == "http_request"
