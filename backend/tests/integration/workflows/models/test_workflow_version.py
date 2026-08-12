"""Unit tests for WorkflowVersion model.

Tests cover:
- WorkflowVersion creation with required fields
- Soft delete behavior
- Unique (workflow_id, version) constraint
- Workflow definition storage
- change_description field
- Relationships with Workflow and User
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.models import Workflow, WorkflowVersion
from tests.helpers.workflow import create_minimal_workflow_definition


@pytest.mark.asyncio
async def test_create_workflow_version_with_required_fields(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test creating a workflow version with required fields only."""
    # Create version
    version = WorkflowVersion(
        id=uuid4(),
        workflow_id=test_workflow.id,
        version=2,
        schema_version="2.0.0",
        workflow_definition=create_minimal_workflow_definition(name="test-workflow"),
        created_by=test_user.id,
    )
    test_db_session.add(version)
    await test_db_session.commit()

    assert version.id is not None
    assert version.workflow_id == test_workflow.id
    assert version.version == 2
    assert version.schema_version == "2.0.0"
    assert version.workflow_definition is not None
    assert version.created_by == test_user.id
    assert version.change_description is None
    assert version.deleted_at is None
    assert version.deleted_by is None
    assert version.created_at is not None


@pytest.mark.asyncio
async def test_create_workflow_version_with_all_fields(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test creating a workflow version with all fields."""
    version = WorkflowVersion(
        id=uuid4(),
        workflow_id=test_workflow.id,
        version=2,
        schema_version="2.0.0",
        workflow_definition=create_minimal_workflow_definition(name="full-workflow"),
        created_by=test_user.id,
        change_description="Initial version",
    )
    test_db_session.add(version)
    await test_db_session.commit()

    assert version.change_description == "Initial version"


@pytest.mark.asyncio
async def test_workflow_version_soft_delete(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test soft delete sets deleted_at and deleted_by correctly."""
    version = WorkflowVersion(
        id=uuid4(),
        workflow_id=test_workflow.id,
        version=2,
        schema_version="2.0.0",
        workflow_definition=create_minimal_workflow_definition(name="test"),
        created_by=test_user.id,
    )
    test_db_session.add(version)
    await test_db_session.commit()

    # Perform soft delete
    now = datetime.now(UTC)
    version.deleted_at = now
    version.deleted_by = test_user.id
    await test_db_session.commit()

    assert version.deleted_at == now
    assert version.deleted_by == test_user.id


@pytest.mark.asyncio
async def test_workflow_version_unique_workflow_version_constraint(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test that (workflow_id, version) must be unique."""
    # Create first version
    version1 = WorkflowVersion(
        id=uuid4(),
        workflow_id=test_workflow.id,
        version=2,
        schema_version="2.0.0",
        workflow_definition=create_minimal_workflow_definition(name="v2"),
        created_by=test_user.id,
    )
    test_db_session.add(version1)
    await test_db_session.commit()

    # Try to create duplicate version
    version2 = WorkflowVersion(
        id=uuid4(),
        workflow_id=test_workflow.id,
        version=2,  # Same version number
        schema_version="2.0.0",
        workflow_definition=create_minimal_workflow_definition(name="v2-duplicate"),
        created_by=test_user.id,
    )
    test_db_session.add(version2)

    with pytest.raises(IntegrityError):
        await test_db_session.commit()

    await test_db_session.rollback()


@pytest.mark.asyncio
async def test_workflow_version_multiple_versions_same_workflow(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test creating multiple versions for the same workflow."""
    # Create multiple versions (starting from 2 since fixture creates version 1)
    for i in range(2, 5):
        version = WorkflowVersion(
            id=uuid4(),
            workflow_id=test_workflow.id,
            version=i,
            schema_version="2.0.0",
            workflow_definition=create_minimal_workflow_definition(name=f"v{i}"),
            created_by=test_user.id,
            change_description=f"Version {i}",
        )
        test_db_session.add(version)

    await test_db_session.commit()

    # Query all versions
    result = await test_db_session.exec(
        select(WorkflowVersion).filter(
            WorkflowVersion.workflow_id == test_workflow.id,  # type: ignore[arg-type]
            WorkflowVersion.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    versions = list(result.all())

    assert len(versions) == 4  # 1 from fixture + 3 created here
    assert {v.version for v in versions} == {1, 2, 3, 4}


@pytest.mark.asyncio
async def test_workflow_version_relationship_with_workflow(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test relationship between WorkflowVersion and Workflow."""
    version = WorkflowVersion(
        id=uuid4(),
        workflow_id=test_workflow.id,
        version=2,
        schema_version="2.0.0",
        workflow_definition=create_minimal_workflow_definition(name="test"),
        created_by=test_user.id,
    )
    test_db_session.add(version)
    await test_db_session.commit()

    # Access workflow relationship
    assert version.workflow.id == test_workflow.id
    assert version.workflow.name == test_workflow.name

    # Access versions from workflow
    await test_db_session.refresh(test_workflow, ["versions"])
    assert len(test_workflow.versions) == 2  # One from fixture, one created here
    version_ids = {v.id for v in test_workflow.versions}
    assert version.id in version_ids


@pytest.mark.asyncio
async def test_workflow_version_relationship_with_user(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test that WorkflowVersion tracks created_by user ID."""
    version = WorkflowVersion(
        id=uuid4(),
        workflow_id=test_workflow.id,
        version=2,  # Use version 2 since fixture already has version 1
        schema_version="2.0.0",
        workflow_definition=create_minimal_workflow_definition(name="test"),
        created_by=test_user.id,
    )
    test_db_session.add(version)
    await test_db_session.commit()

    # Verify created_by field references the user
    assert version.created_by == test_user.id


@pytest.mark.asyncio
async def test_workflow_version_repr(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test string representation of WorkflowVersion."""
    version_id = uuid4()
    version = WorkflowVersion(
        id=version_id,
        workflow_id=test_workflow.id,
        version=2,
        schema_version="2.0.0",
        workflow_definition=create_minimal_workflow_definition(name="test"),
        created_by=test_user.id,
    )

    repr_str = repr(version)
    assert "WorkflowVersion" in repr_str
    assert str(version_id) in repr_str
    assert str(test_workflow.id) in repr_str
    assert "2" in repr_str


@pytest.mark.asyncio
async def test_workflow_version_workflow_definition_storage(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
) -> None:
    """Test that large workflow definitions are stored correctly."""
    # Create a larger workflow definition
    large_definition = create_minimal_workflow_definition(
        name="large-workflow",
        description="A workflow with many activities",
    )

    version = WorkflowVersion(
        id=uuid4(),
        workflow_id=test_workflow.id,
        version=2,  # Use version 2 since fixture already has version 1
        schema_version="2.0.0",
        workflow_definition=large_definition,
        created_by=test_user.id,
    )
    test_db_session.add(version)
    await test_db_session.commit()

    assert version.workflow_definition is not None
    assert version.workflow_definition.get("name") == "large-workflow"
    assert "nodes" in version.workflow_definition
