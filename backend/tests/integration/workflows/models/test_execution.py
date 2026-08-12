"""Unit tests for Execution model.

Tests cover:
- Execution creation with required fields
- Execution creation with all fields
- Soft delete behavior
- Labels JSONB operations
- Input data JSONB operations
- Status field and enum values
- completed_at constraint (must be after created_at)
- Field defaults (status, labels, input_data)
- Relationships with Workflow, WorkflowVersion, and User
- String representation
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.models import Execution, ExecutionStatus, Workflow, WorkflowVersion


@pytest_asyncio.fixture
async def test_workflow_version(
    test_db_session: AsyncSession,
    test_workflow: Workflow,
) -> WorkflowVersion:
    """Get the workflow version for testing.

    This fixture eagerly loads and returns the workflow version from test_workflow.
    """
    await test_db_session.refresh(test_workflow, ["versions"])
    return test_workflow.versions[0]


@pytest.mark.asyncio
async def test_create_execution_with_required_fields(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    test_workflow_version: WorkflowVersion,
) -> None:
    """Test creating an execution with required fields only."""
    # Create execution
    execution = Execution(
        id=uuid4(),
        workflow_id=test_workflow.id,
        workflow_version_id=test_workflow_version.id,
        temporal_workflow_id="test-workflow-123",
        created_by=test_user.id,
        updated_by=test_user.id,
        project_id=test_workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    assert execution.id is not None
    assert execution.workflow_id == test_workflow.id
    assert execution.workflow_version_id == test_workflow_version.id
    assert execution.temporal_workflow_id == "test-workflow-123"
    assert execution.status == ExecutionStatus.PENDING
    assert execution.created_by == test_user.id
    assert execution.updated_by == test_user.id
    assert execution.completed_at is None
    assert execution.input_data == {}
    assert execution.error_details is None
    assert execution.labels == {}
    assert execution.deleted_at is None
    assert execution.deleted_by is None
    assert execution.created_at is not None
    assert execution.updated_at is not None


@pytest.mark.asyncio
async def test_create_execution_with_all_fields(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    test_workflow_version: WorkflowVersion,
) -> None:
    """Test creating an execution with all fields."""
    labels = {"environment": "production", "priority": "high"}
    input_data = {"param1": "value1", "param2": 42}

    execution = Execution(
        id=uuid4(),
        workflow_id=test_workflow.id,
        workflow_version_id=test_workflow_version.id,
        temporal_workflow_id="test-workflow-456",
        status=ExecutionStatus.COMPLETED,
        created_by=test_user.id,
        updated_by=test_user.id,
        input_data=input_data,
        error_details="Test error details",
        labels=labels,
        project_id=test_workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    assert execution.status == ExecutionStatus.COMPLETED
    assert execution.input_data == input_data
    assert execution.error_details == "Test error details"
    assert execution.labels == labels


@pytest.mark.asyncio
async def test_execution_soft_delete(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    test_workflow_version: WorkflowVersion,
) -> None:
    """Test soft delete sets deleted_at and deleted_by correctly."""
    # Create execution
    execution = Execution(
        id=uuid4(),
        workflow_id=test_workflow.id,
        workflow_version_id=test_workflow_version.id,
        temporal_workflow_id="test-workflow-789",
        created_by=test_user.id,
        updated_by=test_user.id,
        project_id=test_workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    # Perform soft delete
    now = datetime.now(UTC)
    execution.deleted_at = now
    execution.deleted_by = test_user.id
    await test_db_session.commit()

    assert execution.deleted_at == now
    assert execution.deleted_by == test_user.id


@pytest.mark.asyncio
async def test_execution_labels_jsonb_operations(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    test_workflow_version: WorkflowVersion,
) -> None:
    """Test JSONB labels can be queried and updated."""
    # Create execution with labels
    labels = {"env": "dev", "region": "us-east-1"}
    execution = Execution(
        id=uuid4(),
        workflow_id=test_workflow.id,
        workflow_version_id=test_workflow_version.id,
        temporal_workflow_id="test-workflow-labels",
        labels=labels,
        created_by=test_user.id,
        updated_by=test_user.id,
        project_id=test_workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    assert execution.labels == labels

    # Update labels (all values must be strings per spec 006)
    execution.labels = {"env": "prod", "region": "us-west-2", "critical": "true"}
    await test_db_session.commit()

    assert execution.labels["env"] == "prod"
    assert execution.labels["critical"] == "true"


@pytest.mark.asyncio
async def test_execution_input_data_jsonb_operations(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    test_workflow_version: WorkflowVersion,
) -> None:
    """Test JSONB input_data can be stored and retrieved."""
    # Create execution with complex input data
    input_data = {
        "string_param": "value",
        "number_param": 42,
        "bool_param": True,
        "nested_param": {"key": "value", "count": 10},
        "array_param": [1, 2, 3],
    }
    execution = Execution(
        id=uuid4(),
        workflow_id=test_workflow.id,
        workflow_version_id=test_workflow_version.id,
        temporal_workflow_id="test-workflow-input",
        input_data=input_data,
        created_by=test_user.id,
        updated_by=test_user.id,
        project_id=test_workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    assert execution.input_data == input_data
    assert execution.input_data["string_param"] == "value"
    assert execution.input_data["number_param"] == 42
    assert execution.input_data["nested_param"]["count"] == 10


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_execution_status_enum_values(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    test_workflow_version: WorkflowVersion,
) -> None:
    """Test all ExecutionStatus enum values."""
    statuses = [
        ExecutionStatus.PENDING,
        ExecutionStatus.RUNNING,
        ExecutionStatus.PAUSED,
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
    ]

    for i, status in enumerate(statuses):
        execution = Execution(
            id=uuid4(),
            workflow_id=test_workflow.id,
            workflow_version_id=test_workflow_version.id,
            temporal_workflow_id=f"test-workflow-status-{i}",
            status=status,
            created_by=test_user.id,
            updated_by=test_user.id,
            project_id=test_workflow.project_id,
        )
        test_db_session.add(execution)

    await test_db_session.commit()


@pytest.mark.asyncio
async def test_execution_completed_at_constraint_valid(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    test_workflow_version: WorkflowVersion,
) -> None:
    """Test that completed_at can be after created_at."""
    execution = Execution(
        id=uuid4(),
        workflow_id=test_workflow.id,
        workflow_version_id=test_workflow_version.id,
        temporal_workflow_id="test-workflow-valid-time",
        created_by=test_user.id,
        updated_by=test_user.id,
        project_id=test_workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    # Set completed_at to be after created_at
    completed_time = execution.created_at + timedelta(minutes=5)
    execution.completed_at = completed_time
    await test_db_session.commit()

    assert execution.completed_at is not None
    assert execution.completed_at > execution.created_at


@pytest.mark.asyncio
async def test_execution_completed_at_constraint_invalid(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    test_workflow_version: WorkflowVersion,
) -> None:
    """Test that completed_at cannot be before created_at."""
    execution = Execution(
        id=uuid4(),
        workflow_id=test_workflow.id,
        workflow_version_id=test_workflow_version.id,
        temporal_workflow_id="test-workflow-invalid-time",
        created_by=test_user.id,
        updated_by=test_user.id,
        project_id=test_workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    # Try to set completed_at to be before created_at
    invalid_time = execution.created_at - timedelta(minutes=5)
    execution.completed_at = invalid_time

    with pytest.raises(IntegrityError) as exc_info:
        await test_db_session.commit()

    assert "check_execution_completed_at_after_created_at" in str(exc_info.value)
    await test_db_session.rollback()


@pytest.mark.asyncio
async def test_execution_status_default(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    test_workflow_version: WorkflowVersion,
) -> None:
    """Test that status defaults to PENDING."""
    execution = Execution(
        id=uuid4(),
        workflow_id=test_workflow.id,
        workflow_version_id=test_workflow_version.id,
        temporal_workflow_id="test-workflow-default-status",
        created_by=test_user.id,
        updated_by=test_user.id,
        project_id=test_workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    assert execution.status == ExecutionStatus.PENDING


@pytest.mark.asyncio
async def test_execution_labels_default(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    test_workflow_version: WorkflowVersion,
) -> None:
    """Test that labels defaults to empty dict."""
    execution = Execution(
        id=uuid4(),
        workflow_id=test_workflow.id,
        workflow_version_id=test_workflow_version.id,
        temporal_workflow_id="test-workflow-default-labels",
        created_by=test_user.id,
        updated_by=test_user.id,
        project_id=test_workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    assert execution.labels == {}
    assert isinstance(execution.labels, dict)


@pytest.mark.asyncio
async def test_execution_input_data_default(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    test_workflow_version: WorkflowVersion,
) -> None:
    """Test that input_data defaults to empty dict."""
    execution = Execution(
        id=uuid4(),
        workflow_id=test_workflow.id,
        workflow_version_id=test_workflow_version.id,
        temporal_workflow_id="test-workflow-default-input",
        created_by=test_user.id,
        updated_by=test_user.id,
        project_id=test_workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    assert execution.input_data == {}
    assert isinstance(execution.input_data, dict)


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_execution_relationship_with_workflow(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    test_workflow_version: WorkflowVersion,
) -> None:
    """Test relationship between Execution and Workflow."""
    execution = Execution(
        id=uuid4(),
        workflow_id=test_workflow.id,
        workflow_version_id=test_workflow_version.id,
        temporal_workflow_id="test-workflow-rel",
        created_by=test_user.id,
        updated_by=test_user.id,
        project_id=test_workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    # Access workflow relationship
    assert execution.workflow.id == test_workflow.id
    assert execution.workflow.name == test_workflow.name

    # Access executions from workflow
    await test_db_session.refresh(test_workflow, ["executions"])
    assert len(test_workflow.executions) == 1
    assert test_workflow.executions[0].id == execution.id


@pytest.mark.asyncio
async def test_execution_relationship_with_workflow_version(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    test_workflow_version: WorkflowVersion,
) -> None:
    """Test relationship between Execution and WorkflowVersion."""
    execution = Execution(
        id=uuid4(),
        workflow_id=test_workflow.id,
        workflow_version_id=test_workflow_version.id,
        temporal_workflow_id="test-workflow-version-rel",
        created_by=test_user.id,
        updated_by=test_user.id,
        project_id=test_workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    # Access workflow_version relationship
    assert execution.workflow_version.id == test_workflow_version.id
    assert execution.workflow_version.version == test_workflow_version.version

    # Access executions from workflow_version
    await test_db_session.refresh(test_workflow_version, ["executions"])
    assert len(test_workflow_version.executions) == 1
    assert test_workflow_version.executions[0].id == execution.id


@pytest.mark.asyncio
async def test_execution_relationship_with_user(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    test_workflow_version: WorkflowVersion,
) -> None:
    """Test that Execution tracks created_by and updated_by user IDs."""
    execution = Execution(
        id=uuid4(),
        workflow_id=test_workflow.id,
        workflow_version_id=test_workflow_version.id,
        temporal_workflow_id="test-workflow-user-rel",
        created_by=test_user.id,
        updated_by=test_user.id,
        project_id=test_workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    # Verify created_by and updated_by fields reference the user
    assert execution.created_by == test_user.id
    assert execution.updated_by == test_user.id


@pytest.mark.asyncio
async def test_execution_temporal_workflow_id_unique(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    test_workflow_version: WorkflowVersion,
) -> None:
    """Test that temporal_workflow_id must be unique."""
    # Create first execution
    execution1 = Execution(
        id=uuid4(),
        workflow_id=test_workflow.id,
        workflow_version_id=test_workflow_version.id,
        temporal_workflow_id="unique-temporal-id",
        created_by=test_user.id,
        updated_by=test_user.id,
        project_id=test_workflow.project_id,
    )
    test_db_session.add(execution1)
    await test_db_session.commit()

    # Try to create execution with duplicate temporal_workflow_id
    execution2 = Execution(
        id=uuid4(),
        workflow_id=test_workflow.id,
        workflow_version_id=test_workflow_version.id,
        temporal_workflow_id="unique-temporal-id",  # Duplicate
        created_by=test_user.id,
        updated_by=test_user.id,
        project_id=test_workflow.project_id,
    )
    test_db_session.add(execution2)

    with pytest.raises(IntegrityError):
        await test_db_session.commit()

    await test_db_session.rollback()


@pytest.mark.asyncio
async def test_execution_repr(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    test_workflow_version: WorkflowVersion,
) -> None:
    """Test string representation of Execution."""
    execution_id = uuid4()
    execution = Execution(
        id=execution_id,
        workflow_id=test_workflow.id,
        workflow_version_id=test_workflow_version.id,
        temporal_workflow_id="repr-temporal-id",
        status=ExecutionStatus.RUNNING,
        created_by=test_user.id,
        updated_by=test_user.id,
        project_id=test_workflow.project_id,
    )

    repr_str = repr(execution)
    assert "Execution" in repr_str
    assert str(execution_id) in repr_str


@pytest.mark.asyncio
async def test_execution_error_details_storage(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    test_workflow_version: WorkflowVersion,
) -> None:
    """Test that error_details can store large error messages."""
    large_error = "Error: " + "x" * 1000  # Large error message

    execution = Execution(
        id=uuid4(),
        workflow_id=test_workflow.id,
        workflow_version_id=test_workflow_version.id,
        temporal_workflow_id="test-workflow-error",
        status=ExecutionStatus.FAILED,
        error_details=large_error,
        created_by=test_user.id,
        updated_by=test_user.id,
        project_id=test_workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()

    assert execution.error_details == large_error
    assert len(execution.error_details) > 1000
