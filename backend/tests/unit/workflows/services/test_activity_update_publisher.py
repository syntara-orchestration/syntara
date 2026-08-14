"""Unit tests for ActivityUpdatePublisher.

These tests verify the publisher logic for streaming activity updates to Redis.
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from unittest.mock import patch as mock_patch
from uuid import uuid4

import pytest
from jsonpatch import JsonPatch  # type: ignore[import-untyped]
from redis.exceptions import ConnectionError as RedisConnectionError

from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.services.activity_update_publisher import ActivityUpdatePublisher


@pytest.fixture
def execution_with_activities() -> Execution:
    """Create test execution with activities."""
    execution_id = uuid4()

    # Create activities
    activities = [
        ActivityExecution(
            id=uuid4(),
            execution_id=execution_id,
            activity_name="step1",
            node_type="script",
            temporal_activity_id=f"temporal-step1-{uuid4()}",
            status=ActivityStatus.COMPLETED,
            started_at=datetime(2024, 1, 20, 10, 0, 0, tzinfo=UTC),
            completed_at=datetime(2024, 1, 20, 10, 5, 0, tzinfo=UTC),
            retry_count=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        ActivityExecution(
            id=uuid4(),
            execution_id=execution_id,
            activity_name="step2",
            node_type="script",
            temporal_activity_id=f"temporal-step2-{uuid4()}",
            status=ActivityStatus.RUNNING,
            started_at=datetime(2024, 1, 20, 10, 5, 0, tzinfo=UTC),
            completed_at=None,
            retry_count=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    ]

    # Create execution
    execution = Execution(
        id=execution_id,
        workflow_id=uuid4(),
        workflow_version_id=uuid4(),
        temporal_workflow_id=f"temporal-exec-{execution_id}",
        status=ExecutionStatus.RUNNING,
        created_by=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        updated_by=uuid4(),
        input_data={},
        labels={},
        project_id=uuid4(),
    )
    execution.activities = activities

    return execution


@pytest.fixture
def mock_stream_client() -> AsyncMock:
    """Create mock StreamClient configured for async context manager."""
    mock_client = AsyncMock()
    mock_client.publish = AsyncMock(return_value="1642680000000-0")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


class TestPublishSnapshot:
    """Tests for publish_snapshot method."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("snapshot_type", "execution_status", "expected_event_id"),
        [
            ("initial_snapshot", ExecutionStatus.RUNNING, "1642680000000-0"),
            ("final_snapshot", ExecutionStatus.COMPLETED, "1642680999999-5"),
        ],
    )
    async def test_publishes_snapshot(
        self,
        execution_with_activities: Execution,
        mock_stream_client: AsyncMock,
        snapshot_type: str,
        execution_status: ExecutionStatus,
        expected_event_id: str,
    ) -> None:
        """Test publishing snapshot with execution data."""
        # Arrange
        publisher = ActivityUpdatePublisher()
        execution_with_activities.status = execution_status
        mock_stream_client.publish.return_value = expected_event_id

        with mock_patch(
            "syntara.workflows.services.activity_update_publisher.StreamClient", return_value=mock_stream_client
        ):
            # Act
            event_id = await publisher.publish_snapshot(execution_with_activities, snapshot_type=snapshot_type)  # type: ignore[arg-type]

            # Assert
            assert event_id == expected_event_id

            # Verify publish call
            mock_stream_client.publish.assert_called_once()
            call_args = mock_stream_client.publish.call_args
            stream_id = call_args[0][0]
            message_data = call_args[0][1]

            assert stream_id == f"execution:{execution_with_activities.id}:events"
            assert message_data["type"] == snapshot_type
            assert message_data["execution_id"] == str(execution_with_activities.id)
            assert "timestamp" in message_data
            assert "event_id" not in message_data  # Excluded from publish
            assert len(message_data["execution"]["activities"]) == 2
            assert message_data["execution"]["activities"][0]["activity_id"] == "step1"
            assert message_data["execution"]["activities"][0]["status"] == "completed"
            assert message_data["execution"]["activities"][1]["activity_id"] == "step2"
            assert message_data["execution"]["activities"][1]["status"] == "running"

    @pytest.mark.asyncio
    async def test_publishes_snapshot_with_empty_activities(self, mock_stream_client: AsyncMock) -> None:
        """Test publishing snapshot when execution has no activities."""
        # Arrange
        publisher = ActivityUpdatePublisher()
        execution_id = uuid4()
        execution = Execution(
            id=execution_id,
            workflow_id=uuid4(),
            workflow_version_id=uuid4(),
            temporal_workflow_id=f"temporal-exec-{execution_id}",
            status=ExecutionStatus.RUNNING,
            created_by=uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            updated_by=uuid4(),
            input_data={},
            labels={},
            project_id=uuid4(),
        )
        execution.activities = []

        with mock_patch(
            "syntara.workflows.services.activity_update_publisher.StreamClient", return_value=mock_stream_client
        ):
            # Act
            event_id = await publisher.publish_snapshot(execution, snapshot_type="initial_snapshot")

            # Assert
            assert event_id == "1642680000000-0"

            call_args = mock_stream_client.publish.call_args
            message_data = call_args[0][1]
            assert message_data["execution"]["activities"] == []


class TestPublishActivityPatch:
    """Tests for publish_activity_patch method."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("old_state", "new_state", "expected_ops_count", "expected_event_id"),
        [
            # Single operation: status change
            (
                [{"activity_id": "step1", "status": "running"}],
                [{"activity_id": "step1", "status": "completed"}],
                1,
                "1642680123456-1",
            ),
            # Multiple operations: multiple field updates
            (
                [
                    {"activity_id": "step1", "status": "running"},
                    {"activity_id": "step2", "status": "pending"},
                ],
                [
                    {"activity_id": "step1", "status": "completed", "completed_at": "2024-01-20T10:30:00Z"},
                    {"activity_id": "step2", "status": "running", "started_at": "2024-01-20T10:30:00Z"},
                ],
                4,  # Two status updates + two timestamp additions
                "1642680123456-2",
            ),
        ],
    )
    async def test_publishes_patch_operations(
        self,
        mock_stream_client: AsyncMock,
        old_state: list[dict[str, Any]],
        new_state: list[dict[str, Any]],
        expected_ops_count: int,
        expected_event_id: str,
    ) -> None:
        """Test publishing JSON Patch operations."""
        # Arrange
        publisher = ActivityUpdatePublisher()
        execution_id = uuid4()
        patch = JsonPatch.from_diff(old_state, new_state)
        mock_stream_client.publish.return_value = expected_event_id

        with mock_patch(
            "syntara.workflows.services.activity_update_publisher.StreamClient", return_value=mock_stream_client
        ):
            # Act
            event_id = await publisher.publish_activity_patch(execution_id, [patch])

            # Assert
            assert event_id == expected_event_id

            # Verify publish call
            call_args = mock_stream_client.publish.call_args
            stream_id = call_args[0][0]
            message_data = call_args[0][1]

            assert stream_id == f"execution:{execution_id}:events"
            assert message_data["type"] == "activity_patch"
            assert message_data["execution_id"] == str(execution_id)
            assert "timestamp" in message_data
            assert "event_id" not in message_data  # Excluded from publish
            assert len(message_data["ops"]) == expected_ops_count

    @pytest.mark.asyncio
    async def test_publishes_patch_with_move_operation(self, mock_stream_client: AsyncMock) -> None:
        """Test publishing patch with 'move' operation containing 'from' field."""
        # Arrange
        publisher = ActivityUpdatePublisher()
        execution_id = uuid4()

        # Create a patch with move operation (has 'from' field)
        patch_dict = {
            "op": "move",
            "from": "/activities/0",
            "path": "/activities/1",
        }
        patch = JsonPatch([patch_dict])

        with mock_patch(
            "syntara.workflows.services.activity_update_publisher.StreamClient", return_value=mock_stream_client
        ):
            # Act
            event_id = await publisher.publish_activity_patch(execution_id, [patch])

            # Assert
            assert event_id == "1642680000000-0"

            # Verify 'from' field is preserved (uses alias)
            call_args = mock_stream_client.publish.call_args
            message_data = call_args[0][1]
            assert len(message_data["ops"]) == 1
            assert message_data["ops"][0]["op"] == "move"
            assert message_data["ops"][0]["from"] == "/activities/0"  # 'from' should be preserved
            assert message_data["ops"][0]["path"] == "/activities/1"

    @pytest.mark.asyncio
    async def test_publishes_empty_patch_list(self, mock_stream_client: AsyncMock) -> None:
        """Test publishing with empty patch list."""
        # Arrange
        publisher = ActivityUpdatePublisher()
        execution_id = uuid4()

        with mock_patch(
            "syntara.workflows.services.activity_update_publisher.StreamClient", return_value=mock_stream_client
        ):
            # Act
            event_id = await publisher.publish_activity_patch(execution_id, [])

            # Assert
            assert event_id == "1642680000000-0"

            # Verify empty ops list
            call_args = mock_stream_client.publish.call_args
            message_data = call_args[0][1]
            assert message_data["ops"] == []


class TestPublishExecutionPatch:
    """Tests for publish_execution_patch method."""

    @pytest.mark.asyncio
    async def test_publishes_status_patch(self, mock_stream_client: AsyncMock) -> None:
        """Test publishing execution status change as JSON Patch."""
        from syntara.workflows.models.visualization import JsonPatchOperation

        publisher = ActivityUpdatePublisher()
        execution_id = uuid4()
        ops = [JsonPatchOperation(op="replace", path="/status", value="running")]

        with mock_patch(
            "syntara.workflows.services.activity_update_publisher.StreamClient", return_value=mock_stream_client
        ):
            event_id = await publisher.publish_execution_patch(execution_id, ops)

            assert event_id == "1642680000000-0"

            call_args = mock_stream_client.publish.call_args
            stream_id = call_args[0][0]
            message_data = call_args[0][1]

            assert stream_id == f"execution:{execution_id}:events"
            assert message_data["type"] == "execution_patch"
            assert message_data["execution_id"] == str(execution_id)
            assert "timestamp" in message_data
            assert "event_id" not in message_data
            assert len(message_data["ops"]) == 1
            assert message_data["ops"][0]["op"] == "replace"
            assert message_data["ops"][0]["path"] == "/status"
            assert message_data["ops"][0]["value"] == "running"

    @pytest.mark.asyncio
    async def test_publishes_multiple_ops(self, mock_stream_client: AsyncMock) -> None:
        """Test publishing multiple execution-level patch operations."""
        from syntara.workflows.models.visualization import JsonPatchOperation

        publisher = ActivityUpdatePublisher()
        execution_id = uuid4()
        ops = [
            JsonPatchOperation(op="replace", path="/status", value="paused"),
            JsonPatchOperation(op="replace", path="/updated_at", value="2024-01-20T10:30:00Z"),
        ]

        with mock_patch(
            "syntara.workflows.services.activity_update_publisher.StreamClient", return_value=mock_stream_client
        ):
            event_id = await publisher.publish_execution_patch(execution_id, ops)

            assert event_id == "1642680000000-0"
            call_args = mock_stream_client.publish.call_args
            message_data = call_args[0][1]
            assert len(message_data["ops"]) == 2


class TestRedisFailurePropagates:
    """Publisher methods must raise on failure, not swallow it.

    ActivitySyncService (the only real caller) already wraps every call in
    try/except Exception and logs "non-fatal" — that's the single place
    Redis-outage handling belongs. If the publisher swallowed failures too,
    the sync service's success-path debug log would fire even when nothing
    was published, silently hiding the outage.
    """

    @staticmethod
    def _unavailable_stream_client() -> AsyncMock:
        """A StreamClient mock whose publish() always raises RedisConnectionError."""
        mock_client = AsyncMock()
        mock_client.publish = AsyncMock(side_effect=RedisConnectionError("pool exhausted"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        return mock_client

    @pytest.mark.asyncio
    async def test_publish_snapshot_raises_on_redis_failure(self, execution_with_activities: Execution) -> None:
        publisher = ActivityUpdatePublisher()
        unavailable_client = self._unavailable_stream_client()

        with (
            mock_patch(
                "syntara.workflows.services.activity_update_publisher.StreamClient", return_value=unavailable_client
            ),
            pytest.raises(RedisConnectionError),
        ):
            await publisher.publish_snapshot(execution_with_activities, snapshot_type="initial_snapshot")

    @pytest.mark.asyncio
    async def test_publish_activity_patch_raises_on_redis_failure(self) -> None:
        publisher = ActivityUpdatePublisher()
        execution_id = uuid4()
        patch = JsonPatch.from_diff(
            [{"activity_id": "step1", "status": "running"}],
            [{"activity_id": "step1", "status": "completed"}],
        )
        unavailable_client = self._unavailable_stream_client()

        with (
            mock_patch(
                "syntara.workflows.services.activity_update_publisher.StreamClient", return_value=unavailable_client
            ),
            pytest.raises(RedisConnectionError),
        ):
            await publisher.publish_activity_patch(execution_id, [patch])

    @pytest.mark.asyncio
    async def test_publish_execution_patch_raises_on_redis_failure(self) -> None:
        from syntara.workflows.models.visualization import JsonPatchOperation

        publisher = ActivityUpdatePublisher()
        execution_id = uuid4()
        ops = [JsonPatchOperation(op="replace", path="/status", value="running")]
        unavailable_client = self._unavailable_stream_client()

        with (
            mock_patch(
                "syntara.workflows.services.activity_update_publisher.StreamClient", return_value=unavailable_client
            ),
            pytest.raises(RedisConnectionError),
        ):
            await publisher.publish_execution_patch(execution_id, ops)
