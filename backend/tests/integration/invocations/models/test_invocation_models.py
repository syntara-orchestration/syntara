"""Unit tests for Invocation SQLModel.

This file contains comprehensive tests for the Invocation model, covering both
ORM (database) usage and Pydantic (schema validation) usage.

Tests cover:
- Database operations (creation, updates, queries)
- Status transitions and enum handling
- JSONB field operations (context_data, result, checkpoint_data)
- Timestamp field behavior (created_at, started_at, completed_at, updated_at)
- Field validation and constraints
- List response models (InvocationListResponse)
- Enum validation (InvocationStatus)
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import inspect
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models import Invocation, InvocationListResponse, InvocationStatus
from syntara.core.models import User


@pytest.mark.asyncio
async def test_create_invocation_with_required_fields(
    test_db_session: AsyncSession, test_user: User, test_project_id
) -> None:
    """Test creating an invocation with required fields only."""
    invocation = Invocation(
        prompt="Deploy customer service app to production",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-001",
        status=InvocationStatus.RUNNING,
    )

    test_db_session.add(invocation)
    await test_db_session.commit()

    # Verify required fields
    assert invocation.id is not None
    assert invocation.prompt == "Deploy customer service app to production"
    assert invocation.created_by == test_user.id
    assert invocation.session_id == "session-001"
    assert invocation.status == InvocationStatus.RUNNING

    # Verify auto-generated fields
    assert invocation.created_at is not None
    assert invocation.updated_at is not None

    # Verify optional fields are None/empty
    assert invocation.started_at is None
    assert invocation.completed_at is None
    assert invocation.context_data == {}
    assert invocation.result is None
    assert invocation.error_message is None
    assert invocation.checkpoint_data is None


@pytest.mark.asyncio
async def test_create_invocation_with_all_fields(
    test_db_session: AsyncSession, test_user: User, test_project_id
) -> None:
    """Test creating an invocation with all fields populated."""
    now = datetime.now(UTC)

    invocation = Invocation(
        prompt="Analyze production metrics",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-002",
        status=InvocationStatus.COMPLETED,
        started_at=now,
        completed_at=now,
        context_data={"environment": "production", "app_id": "app-1"},
        result={"workflow_id": "wf-123", "status": "success"},
        error_message=None,
        checkpoint_data={"phase": "complete", "step": 5},
    )

    test_db_session.add(invocation)
    await test_db_session.commit()

    # Verify all fields
    assert invocation.prompt == "Analyze production metrics"
    assert invocation.created_by == test_user.id
    assert invocation.session_id == "session-002"
    assert invocation.status == InvocationStatus.COMPLETED
    assert invocation.started_at == now
    assert invocation.completed_at == now
    assert invocation.context_data == {"environment": "production", "app_id": "app-1"}
    assert invocation.result == {"workflow_id": "wf-123", "status": "success"}
    assert invocation.checkpoint_data == {"phase": "complete", "step": 5}


@pytest.mark.asyncio
async def test_invocation_status_transitions(test_db_session: AsyncSession, test_user: User, test_project_id) -> None:
    """Test invocation status can be updated."""
    invocation = Invocation(
        prompt="Test workflow",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-003",
        status=InvocationStatus.RUNNING,
    )

    test_db_session.add(invocation)
    await test_db_session.commit()

    # Update status to paused
    invocation.status = InvocationStatus.PAUSED
    await test_db_session.commit()
    assert invocation.status == InvocationStatus.PAUSED

    # Update status to cancelled
    invocation.status = InvocationStatus.CANCELLED
    await test_db_session.commit()
    assert invocation.status == InvocationStatus.CANCELLED


@pytest.mark.asyncio
async def test_invocation_timestamps(test_db_session: AsyncSession, test_user: User, test_project_id) -> None:
    """Test timestamp fields behavior."""
    invocation = Invocation(
        prompt="Test timestamps",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-100",
        status=InvocationStatus.RUNNING,
    )

    test_db_session.add(invocation)
    await test_db_session.commit()

    created_at = invocation.created_at
    updated_at = invocation.updated_at

    # Verify timestamps are set
    assert created_at is not None
    assert updated_at is not None

    # Update the invocation
    invocation.status = InvocationStatus.COMPLETED
    invocation.completed_at = datetime.now(UTC)
    await test_db_session.commit()

    # created_at should not change, updated_at should
    assert invocation.created_at == created_at
    assert invocation.updated_at >= updated_at


@pytest.mark.asyncio
async def test_invocation_jsonb_fields(test_db_session: AsyncSession, test_user: User, test_project_id) -> None:
    """Test JSONB fields can store complex data."""
    complex_context = {
        "environment": "production",
        "region": "us-east-1",
        "metadata": {
            "tags": ["deployment", "critical"],
            "version": "1.2.3",
        },
    }

    invocation = Invocation(
        prompt="Complex JSONB test",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-200",
        status=InvocationStatus.RUNNING,
        context_data=complex_context,
    )

    test_db_session.add(invocation)
    await test_db_session.commit()

    # Verify JSONB data is preserved
    assert invocation.context_data == complex_context
    assert invocation.context_data["metadata"]["tags"] == ["deployment", "critical"]  # type: ignore[index]


@pytest.mark.asyncio
async def test_query_invocations_by_status(test_db_session: AsyncSession, test_user: User, test_project_id) -> None:
    """Test querying invocations by status."""
    # Create multiple invocations with different statuses
    invocation1 = Invocation(
        prompt="Running task 1",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-300",
        status=InvocationStatus.RUNNING,
    )
    invocation2 = Invocation(
        prompt="Running task 2",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-300",
        status=InvocationStatus.RUNNING,
    )
    invocation3 = Invocation(
        prompt="Completed task",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-300",
        status=InvocationStatus.COMPLETED,
    )

    test_db_session.add_all([invocation1, invocation2, invocation3])
    await test_db_session.commit()

    # Query for running invocations
    result = await test_db_session.exec(select(Invocation).where(Invocation.status == "running"))
    running_invocations = result.all()

    assert len(running_invocations) == 2
    assert all(inv.status == "running" for inv in running_invocations)


@pytest.mark.asyncio
async def test_query_invocations_by_user(
    test_db_session: AsyncSession, test_user: User, user_factory: Callable[..., Awaitable[User]], test_project_id
) -> None:
    """Test querying invocations by created_by."""
    # Create a second user for testing
    user2 = await user_factory(
        username="testuser2",
        email="testuser2@example.com",
        first_name="Test",
        last_name="User 2",
    )

    # Create invocations for different users
    invocation1 = Invocation(
        prompt="User 1 task",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-400",
        status=InvocationStatus.RUNNING,
    )
    invocation2 = Invocation(
        prompt="User 2 task",
        created_by=user2.id,
        project_id=test_project_id,
        session_id="session-500",
        status=InvocationStatus.RUNNING,
    )

    test_db_session.add_all([invocation1, invocation2])
    await test_db_session.commit()

    # Query for user1's invocations
    result = await test_db_session.exec(select(Invocation).where(Invocation.created_by == test_user.id))
    user_invocations = result.all()

    assert len(user_invocations) == 1
    assert user_invocations[0].created_by == test_user.id


@pytest.mark.asyncio
async def test_invocation_repr(test_db_session: AsyncSession, test_user: User, test_project_id) -> None:
    """Test __repr__ method."""
    invocation = Invocation(
        prompt="Test repr",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-600",
        status=InvocationStatus.RUNNING,
    )

    test_db_session.add(invocation)
    await test_db_session.commit()

    repr_str = repr(invocation)
    assert "Invocation" in repr_str
    assert str(invocation.id) in repr_str
    assert "running" in repr_str or "RUNNING" in repr_str  # Can be either enum name or value


# SQLModel validation tests (previously in test_invocation_schemas.py)
# These tests validate the Invocation model when used as a Pydantic schema


class TestInvocationValidation:
    """Tests for Invocation SQLModel validation (schema usage)."""

    def test_valid_invocation_creation(self) -> None:
        """Test creating invocation with valid data."""
        invocation_id = uuid4()
        user_uuid = uuid4()
        now = datetime.now(UTC)

        invocation = Invocation(
            id=invocation_id,
            prompt="Deploy app to production",
            created_by=user_uuid,
            project_id=uuid4(),
            session_id="session-001",
            status=InvocationStatus.RUNNING,
            created_at=now,
            updated_at=now,
        )

        assert invocation.id == invocation_id
        assert invocation.prompt == "Deploy app to production"
        assert invocation.created_by == user_uuid
        assert invocation.session_id == "session-001"
        assert invocation.status == InvocationStatus.RUNNING
        assert invocation.started_at is None
        assert invocation.completed_at is None
        assert invocation.context_data == {}
        assert invocation.result is None
        assert invocation.error_message is None

    def test_invocation_with_all_optional_fields(self) -> None:
        """Test invocation with all optional fields populated."""
        invocation_id = uuid4()
        now = datetime.now(UTC)

        invocation = Invocation(
            id=invocation_id,
            prompt="Deploy app",
            created_by=uuid4(),
            project_id=uuid4(),
            session_id="session-001",
            status=InvocationStatus.COMPLETED,
            created_at=now,
            started_at=now,
            completed_at=now,
            updated_at=now,
            context_data={"env": "prod"},
            result={"workflow_id": "wf-123"},
            error_message=None,
            checkpoint_data={"phase": "complete"},
        )

        assert invocation.context_data == {"env": "prod"}
        assert invocation.result == {"workflow_id": "wf-123"}
        assert invocation.checkpoint_data == {"phase": "complete"}


class TestInvocationListResponse:
    """Tests for InvocationListResponse model."""

    def test_empty_list_response(self) -> None:
        """Test list response with no invocations."""
        response = InvocationListResponse(
            resources=[],
            total=0,
        )

        assert response.resources == []
        assert response.total == 0

    def test_list_response_with_invocations(self) -> None:
        """Test list response with multiple invocations."""
        invocation_1 = Invocation(
            id=uuid4(),
            prompt="Test 1",
            created_by=uuid4(),
            project_id=uuid4(),
            session_id="session-001",
            status=InvocationStatus.RUNNING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        invocation_2 = Invocation(
            id=uuid4(),
            prompt="Test 2",
            created_by=uuid4(),
            project_id=uuid4(),
            session_id="session-002",
            status=InvocationStatus.COMPLETED,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        response = InvocationListResponse(
            resources=[invocation_1, invocation_2],
            total=2,
        )

        assert len(response.resources) == 2
        assert response.total == 2


class TestInvocationStatusEnum:
    """Tests for InvocationStatus enum."""

    def test_all_status_enum_values(self) -> None:
        """Test all valid status enum values."""
        assert InvocationStatus.RUNNING.value == "running"
        assert InvocationStatus.PAUSED.value == "paused"
        assert InvocationStatus.CANCELLED.value == "cancelled"
        assert InvocationStatus.COMPLETED.value == "completed"
        assert InvocationStatus.FAILED.value == "failed"

    def test_status_enum_from_string(self) -> None:
        """Test creating status enum from string."""
        status = InvocationStatus("running")
        assert status == InvocationStatus.RUNNING


class TestInvocationBaseResourceFields:
    """Tests for UserOwnedResource base fields (labels, updated_by)."""

    def test_invocation_with_labels(self) -> None:
        """Test creating invocation with labels."""
        labels = {"environment": "production", "region": "us-east-1", "team": "platform"}

        invocation = Invocation(
            id=uuid4(),
            prompt="Test with labels",
            created_by=uuid4(),
            project_id=uuid4(),
            session_id="session-001",
            status=InvocationStatus.RUNNING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            labels=labels,
        )

        assert invocation.labels == labels
        assert invocation.labels["environment"] == "production"
        assert invocation.labels["region"] == "us-east-1"
        assert invocation.labels["team"] == "platform"

    def test_invocation_default_labels_empty(self) -> None:
        """Test invocation has empty dict labels by default (from BaseResource)."""
        invocation = Invocation(
            id=uuid4(),
            prompt="Test default labels",
            created_by=uuid4(),
            project_id=uuid4(),
            session_id="session-001",
            status=InvocationStatus.RUNNING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # BaseResource defaults labels to empty dict {}
        assert invocation.labels == {}

    def test_invocation_with_updated_by(self) -> None:
        """Test invocation with updated_by field."""
        created_by_uuid = uuid4()
        updated_by_uuid = uuid4()

        invocation = Invocation(
            id=uuid4(),
            prompt="Test updated_by",
            created_by=created_by_uuid,
            project_id=uuid4(),
            session_id="session-001",
            status=InvocationStatus.RUNNING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            updated_by=updated_by_uuid,
        )

        assert invocation.created_by == created_by_uuid
        assert invocation.updated_by == updated_by_uuid

    def test_invocation_updated_by_nullable(self) -> None:
        """Test updated_by is nullable (None by default)."""
        invocation = Invocation(
            id=uuid4(),
            prompt="Test nullable updated_by",
            created_by=uuid4(),
            project_id=uuid4(),
            session_id="session-001",
            status=InvocationStatus.RUNNING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert invocation.updated_by is None


class TestInvocationSortableFields:
    """Tests for __sortable_fields__ class variable."""

    def test_sortable_fields_exists(self) -> None:
        """Test that __sortable_fields__ class variable exists."""
        assert hasattr(Invocation, "__sortable_fields__")
        assert isinstance(Invocation.__sortable_fields__, list)

    def test_sortable_fields_contains_correct_fields(self) -> None:
        """Test that __sortable_fields__ contains correct fields."""
        expected_fields = ["created_at", "updated_at", "started_at", "completed_at", "status", "model_name"]
        assert Invocation.__sortable_fields__ == expected_fields

    def test_sortable_fields_are_strings(self) -> None:
        """Test that all sortable fields are strings."""
        assert all(isinstance(field, str) for field in Invocation.__sortable_fields__)


@pytest.mark.asyncio
async def test_query_invocations_by_session_id(test_db_session: AsyncSession, test_user: User, test_project_id) -> None:
    """Test querying invocations by session_id."""
    # Create invocations for different sessions
    invocation1 = Invocation(
        prompt="Session 1 task 1",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-alpha",
        status=InvocationStatus.RUNNING,
    )
    invocation2 = Invocation(
        prompt="Session 1 task 2",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-alpha",
        status=InvocationStatus.RUNNING,
    )
    invocation3 = Invocation(
        prompt="Session 2 task",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-beta",
        status=InvocationStatus.RUNNING,
    )

    test_db_session.add_all([invocation1, invocation2, invocation3])
    await test_db_session.commit()

    # Query for session-alpha invocations
    result = await test_db_session.exec(select(Invocation).where(Invocation.session_id == "session-alpha"))
    session_invocations = result.all()

    assert len(session_invocations) == 2
    assert all(inv.session_id == "session-alpha" for inv in session_invocations)


@pytest.mark.asyncio
async def test_invocation_status_completed(test_db_session: AsyncSession, test_user: User, test_project_id) -> None:
    """Test invocation with COMPLETED status."""
    invocation = Invocation(
        prompt="Test completion",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-700",
        status=InvocationStatus.RUNNING,
    )

    test_db_session.add(invocation)
    await test_db_session.commit()

    # Update to completed
    invocation.status = InvocationStatus.COMPLETED
    invocation.completed_at = datetime.now(UTC)
    await test_db_session.commit()

    assert invocation.status == InvocationStatus.COMPLETED
    assert invocation.completed_at is not None


@pytest.mark.asyncio
async def test_invocation_status_failed(test_db_session: AsyncSession, test_user: User, test_project_id) -> None:
    """Test invocation with FAILED status."""
    invocation = Invocation(
        prompt="Test failure",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-800",
        status=InvocationStatus.RUNNING,
    )

    test_db_session.add(invocation)
    await test_db_session.commit()

    # Update to failed with error message
    invocation.status = InvocationStatus.FAILED
    invocation.error_message = "Tool execution timeout"
    invocation.completed_at = datetime.now(UTC)
    await test_db_session.commit()

    assert invocation.status == InvocationStatus.FAILED
    assert invocation.error_message == "Tool execution timeout"
    assert invocation.completed_at is not None


@pytest.mark.asyncio
async def test_invocation_error_message_field(test_db_session: AsyncSession, test_user: User, test_project_id) -> None:
    """Test error_message field can store error details."""
    error_msg = "Database connection timeout after 30 seconds. Failed to connect to postgres://db:5432"

    invocation = Invocation(
        prompt="Test error message",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-900",
        status=InvocationStatus.FAILED,
        error_message=error_msg,
    )

    test_db_session.add(invocation)
    await test_db_session.commit()

    assert invocation.error_message == error_msg
    assert len(invocation.error_message) > 50  # Verify it can store longer messages


@pytest.mark.asyncio
async def test_invocation_indexes_exist(test_db_session: AsyncSession) -> None:
    """Test that expected indexes exist on invocations table."""

    def get_indexes(connection: Any) -> list[dict[str, Any]]:  # noqa: ANN401
        """Get indexes from the database using sync inspector."""
        inspector = inspect(connection)
        indexes: list[dict[str, Any]] = inspector.get_indexes("invocations")
        return indexes

    # Get the connection and run inspector in sync context
    connection = await test_db_session.connection()
    indexes = await connection.run_sync(get_indexes)
    index_names = {idx["name"] for idx in indexes}

    # Verify expected indexes exist
    expected_indexes = {
        "ix_invocations_status",
        "ix_invocations_created_by",
        "ix_invocations_session_id",
        "ix_invocations_created_at",
        "ix_invocations_created_by_status",
    }

    for expected_index in expected_indexes:
        assert expected_index in index_names, f"Missing index: {expected_index}"


@pytest.mark.asyncio
async def test_invocation_timestamp_timezone_aware(
    test_db_session: AsyncSession, test_user: User, test_project_id
) -> None:
    """Test that timestamp fields preserve timezone information."""
    now = datetime.now(UTC)

    invocation = Invocation(
        prompt="Test timezone awareness",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-1000",
        status=InvocationStatus.RUNNING,
        started_at=now,
    )

    test_db_session.add(invocation)
    await test_db_session.commit()

    # Verify all timestamps have timezone info
    assert invocation.created_at.tzinfo is not None
    assert invocation.updated_at.tzinfo is not None
    assert invocation.started_at is not None
    assert invocation.started_at.tzinfo is not None

    # Verify we can compare timezone-aware datetimes
    assert invocation.created_at.tzinfo == UTC
    assert invocation.updated_at.tzinfo == UTC
    assert invocation.started_at.tzinfo == UTC


@pytest.mark.asyncio
async def test_invocation_session_id_max_length(
    test_db_session: AsyncSession, test_user: User, test_project_id
) -> None:
    """Test session_id field respects max_length constraint."""
    # Create session_id at exactly max length (255 chars)
    max_length_session_id = "s" * 255

    invocation = Invocation(
        prompt="Test session_id max length",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id=max_length_session_id,
        status=InvocationStatus.RUNNING,
    )

    test_db_session.add(invocation)
    await test_db_session.commit()

    assert invocation.session_id == max_length_session_id
    assert len(invocation.session_id) == 255


@pytest.mark.asyncio
async def test_invocation_status_default_value(test_db_session: AsyncSession, test_user: User, test_project_id) -> None:
    """Test that status defaults to CREATED when not specified."""
    invocation = Invocation(
        prompt="Test default status",
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-1100",
        # Note: status not explicitly set
    )

    test_db_session.add(invocation)
    await test_db_session.commit()

    assert invocation.status == InvocationStatus.CREATED


@pytest.mark.asyncio
async def test_invocation_prompt_max_length(test_db_session: AsyncSession, test_user: User, test_project_id) -> None:
    """Test prompt field respects max_length constraint (10000 chars)."""
    # Create prompt at exactly max length (10000 chars)
    max_length_prompt = "a" * 10000

    invocation = Invocation(
        prompt=max_length_prompt,
        created_by=test_user.id,
        project_id=test_project_id,
        session_id="session-1200",
        status=InvocationStatus.RUNNING,
    )

    test_db_session.add(invocation)
    await test_db_session.commit()

    assert invocation.prompt == max_length_prompt
    assert len(invocation.prompt) == 10000
